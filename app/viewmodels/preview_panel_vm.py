# App/viewmodels/preview panel vm.py
import asyncio
import copy
from pathlib import Path
from typing import Any, Dict
from PyQt6.QtCore import QObject, QThreadPool, QTimer, pyqtSignal
from qfluentwidgets import MessageBox
from app.models.mod_item_model import FolderItem, ModStatus
from app.services.Iniparsing_service import IniKeyParsingService, KeyBinding
from app.services.config_service import ConfigService, ConfigSaveError
from app.services.mod_service import ModService
from app.services.persist_utils import find_game_root_from_folder
from app.services.thumbnail_service import ThumbnailService

from app.utils import SystemUtils
from app.viewmodels.mod_list_vm import ModListViewModel
from app.utils.async_utils import Worker
from app.core import i18n as _i18n
from app.utils.logger_utils import logger
from app.utils.image_utils import ImageUtils


class PreviewPanelViewModel(QObject):
    """Manages state and logic for the detailed preview panel."""

    # ---Signals for UI Updates & Feedback ---
    item_loaded = pyqtSignal(object)  # Emits FolderItem to populate the entire panel
    ini_config_loading = pyqtSignal(bool)
    ini_config_ready = pyqtSignal(list)
    is_description_dirty_changed = pyqtSignal(bool)
    toast_requested = pyqtSignal(str, str)  # message, level
    # ---Signals for Cross-ViewModel Communication ---
    item_metadata_saved = pyqtSignal(object)
    ini_dirty_state_changed = pyqtSignal(bool)
    thumbnail_operation_in_progress = pyqtSignal(bool)

    def __init__(
        self,
        mod_service,
        config_service,
        ini_parsing_service,
        thumbnail_service,
        image_utils,
        foldergrid_vm,
        sys_utils,
        note_service=None,
    ):
        super().__init__()
        # ---Injected Services ---
        self.foldergrid_vm: ModListViewModel = foldergrid_vm
        self.sys_utils: SystemUtils = sys_utils
        self.mod_service: ModService = mod_service
        self.config_service: ConfigService = config_service
        self.ini_parsing_service: IniKeyParsingService = ini_parsing_service
        self.image_utils: ImageUtils = image_utils
        self.thumbnail_service: ThumbnailService = thumbnail_service
        self.note_service = note_service
        # ---Internal State ---
        self.current_item_model: FolderItem | None = None
        self.is_description_dirty = False
        self.is_ini_dirty = False
        self._unsaved_ini_changes: Dict[str, Dict[str, Any]] = {}
        self._unsaved_description: str | None = None
        self._notes_dirty = False
        self.editable_keybindings: list[KeyBinding] = (
            []
        )  # A mutable list of KeyBinding objects for live edits

        # --- INI parse cache: item_id → (keybindings, max_mtime) ---
        self._ini_cache: dict[str, tuple[list[KeyBinding], float]] = {}

        # --- Thumbnail operation timeout protection ---
        self._thumbnail_op_timer = QTimer(self)
        self._thumbnail_op_timer.setSingleShot(True)
        self._thumbnail_op_timer.setInterval(30000)  # 30 seconds
        self._thumbnail_op_timer.timeout.connect(self._on_thumbnail_operation_timeout)
        self._thumbnail_op_timed_out = False

    # ---Public Methods (API for the View) ---
    def get_description_editor_height(self) -> int:
        config = self.config_service.load_config()
        return config.description_editor_height or 80

    def save_description_editor_height(self, height: int) -> None:
        height = max(60, min(320, int(height)))
        try:
            self.config_service.save_setting(
                "description_editor_height", height, section="ui"
            )
        except ConfigSaveError as e:
            logger.error(f"Failed to save description editor height: {e}")

    def _create_dict_from_item(self, item: FolderItem) -> dict:
        """Helper to create a view-ready dictionary from a FolderItem model."""
        if not item:
            return {}

        return {
            "id": item.id,
            "actual_name": item.actual_name,
            "is_enabled": (item.status == ModStatus.ENABLED),
            "description": item.description or "",
            "author": item.author or "N/A",
            "tags": item.tags or [],
            "preview_images": item.preview_images or [],
            # ... add other fields needed by view
        }

    # This method was called when the new item was selected from the foldergrid

    def set_current_item(self, item_data: dict | None):
        """Load new item, auto-saving any pending edits first."""
        self._flush_pending_changes_sync()
        self._load_item(item_data)

    def _load_item(self, item_data: dict | None) -> None:
        """Load selected item; parse its .ini files off-UI-thread."""
        if not item_data:
            self.clear_panel()
            return

        # ── locate model ──────────────────────────────────────────────────────
        item_id = item_data.get("id")
        self.current_item_model = next(
            (m for m in self.foldergrid_vm.master_list if m.id == item_id), None
        )

        if not self.current_item_model:
            logger.error("Model not found for item%s", item_id)
            self.clear_panel()
            return

        # ── push basic data to UI immediately ────────────────────────────────
        if isinstance(self.current_item_model, FolderItem):
            self.item_loaded.emit(
                self._create_dict_from_item(self.current_item_model)
            )
        else:
            self.item_loaded.emit(None)

        # ── check INI cache ──────────────────────────────────────────────────────
        folder_path = self.current_item_model.folder_path
        ini_mtimes = [
            p.stat().st_mtime
            for p in folder_path.rglob("*.ini")
            if p.is_file()
        ]
        current_max_mtime = max(ini_mtimes) if ini_mtimes else 0.0

        cached = self._ini_cache.get(item_id)
        if cached is not None:
            cached_bindings, cached_mtime = cached
            if current_max_mtime <= cached_mtime:
                # Cache hit — use cached data directly, no worker needed
                logger.info("INI cache hit for '%s'", self.current_item_model.actual_name)
                self.editable_keybindings = cached_bindings
                self.ini_config_loading.emit(False)
                self._fill_notes_from_file()
                self.original_keybindings = copy.deepcopy(self.editable_keybindings)
                self.ini_config_ready.emit(self.editable_keybindings)
                self.ini_dirty_state_changed.emit(False)
                return

        # ── start async parsing (thread-pool) ─────────────────────────────────────
        logger.info("Async ini-parsing for '%s'", self.current_item_model.actual_name)
        self.ini_config_loading.emit(True)  # show spinner

        # run new async loader in worker thread → no UI freeze
        # Find game root by walking up from the mod folder (most reliable)
        game_root_path = find_game_root_from_folder(folder_path)

        # Fallback: try game.path directly (in case folder walk fails)
        if game_root_path is None and self.foldergrid_vm.current_game and self.foldergrid_vm.current_game.path:
            candidate = self.foldergrid_vm.current_game.path
            if (candidate / "d3dx_user.ini").is_file():
                game_root_path = candidate

        worker = Worker(
            lambda: asyncio.run(
                self.ini_parsing_service.load_keybindings_async(
                    folder_path, game_root_path
                )
            )
        )
        worker.signals.result.connect(self._on_ini_config_loaded)
        worker.signals.error.connect(self._on_ini_config_error)

        thread_pool = QThreadPool.globalInstance()
        if thread_pool is not None:
            thread_pool.start(worker)
        else:
            logger.error(
                "QThreadPool.globalInstance() returned None. Cannot start worker."
            )

    def save_description(self) -> bool:
        """Starting the process of storing the description in the background."""
        if (
            not self.is_description_dirty
            or self._unsaved_description is None
            or not self.current_item_model
        ):
            return False

        logger.info(
            f"Saving description for '{self.current_item_model.actual_name}'..."
        )

        # check if path exists
        if not self.current_item_model.folder_path.exists():
            self.toast_requested.emit(
                _i18n.tr("vm.cannot_save_desc_path"), "error"
            )
            return False

        worker = Worker(
            self.mod_service.update_item_properties,
            self.current_item_model,
            {"description": self._unsaved_description},
        )
        worker.signals.result.connect(self._on_description_saved)
        thread_pool = QThreadPool.globalInstance()
        if thread_pool is not None:
            thread_pool.start(worker)
        else:
            logger.error(
                "QThreadPool.globalInstance() returned None. Cannot start worker."
            )
        return True  # Indicates the storage process begins

    def update_view_for_item(self, new_item_model: FolderItem):
        """
        Flow 3.1b: Updates the view when the currently displayed item is modified
        externally (e.g., from the foldergrid).
        """
        logger.info(
            f"PreviewPanel receiving external update for item:{new_item_model.actual_name}"
        )
        # Invalidate INI cache if folder path changed (e.g. toggle added/removed DISABLED prefix)
        if self.current_item_model and self.current_item_model.folder_path != new_item_model.folder_path:
            self._ini_cache.pop(new_item_model.id, None)
        # Internal State Update
        self.current_item_model = new_item_model
        view_dict = self._create_dict_from_item(new_item_model)
        self.item_loaded.emit(view_dict)

    def save_all_changes(self):
        """Flow 5.2 Part B & D: Saves all pending changes (description, .ini config)."""
        pass

    def add_new_thumbnail(self, image_data):
        """Flow 5.2 Part C: Starts the async process to add a new thumbnail."""
        if not self.current_item_model:
            self.toast_requested.emit(_i18n.tr("vm.no_mod_selected"), "warning")
            return
        if not image_data:
            self.toast_requested.emit(_i18n.tr("vm.no_image_data"), "warning")
            return

        # check if path exists
        if not self.current_item_model.folder_path.exists():
            self.toast_requested.emit(
                _i18n.tr("vm.cannot_add_thumb_path"), "error"
            )
            return

        logger.info(
            f"Starting to add thumbnail for '{self.current_item_model.actual_name}'"
        )
        self.thumbnail_operation_in_progress.emit(True)

        worker = Worker(
            self.mod_service.add_preview_image, self.current_item_model, image_data
        )
        worker.signals.result.connect(self._on_new_thumbnail_operation_finished)
        worker.signals.error.connect(self._on_thumbnail_operation_error)
        thread_pool = QThreadPool.globalInstance()
        if thread_pool is not None:
            thread_pool.start(worker)
        else:
            logger.error(
                "QThreadPool.globalInstance() returned None. Cannot start worker."
            )

    def _handle_thumbnail_operation_result(self, result: dict):
        """
        A generic helper that processes the result from any thumbnail operation.
        This keeps the result-handling logic DRY.
        """
        self.thumbnail_operation_in_progress.emit(False)

        if not result.get("success"):
            error_msg = result.get("error", _i18n.tr("vm.unknown_error"))
            self.toast_requested.emit(error_msg, "error")
            return

        new_item_model = result.get("data")
        if not new_item_model:
            logger.error("Thumbnail operation succeeded but returned no data.")
            return

        # Invalidate cache for any deleted images
        deleted_paths = result.get("deleted_paths", [])
        if deleted_paths:
            logger.info(
                f"Invalidating cache for {len(deleted_paths)} deleted thumbnails."
            )
            for path in deleted_paths:
                self.thumbnail_service.invalidate_cache(new_item_model.id, path)

        # Update state and refresh UI
        self.current_item_model = new_item_model
        self.toast_requested.emit(_i18n.tr("vm.thumb_updated"), "success")
        if self.current_item_model:
            self.item_loaded.emit(self._create_dict_from_item(self.current_item_model))
        self.item_metadata_saved.emit(self.current_item_model)

    def remove_thumbnail(self, image_path: Path):
        """Starts the async process to remove a single thumbnail."""
        if not self.current_item_model:
            self.toast_requested.emit(_i18n.tr("vm.no_mod_selected"), "warning")
            return

        self._start_thumbnail_operation(
            self.mod_service.remove_preview_image,  # Pass function reference
            self._on_thumbnail_operation_complete,  # Pass result slot reference
            self.current_item_model,  # Pass arguments for the function
            image_path,
        )

    def remove_all_thumbnails(self):
        """Starts the async process to remove all thumbnails for the current mod."""
        if not self.current_item_model:
            self.toast_requested.emit(_i18n.tr("vm.no_mod_selected"), "warning")
            return

        self._start_thumbnail_operation(
            self.mod_service.remove_all_preview_images,  # Pass function reference
            self._on_thumbnail_operation_complete,  # Pass result slot reference
            self.current_item_model,  # Pass argument for the function
        )

    def _start_thumbnail_operation(self, service_function, result_slot, *args):
        """
        A generic helper to start any thumbnail-related background task.
        This ensures the function reference (not its result) is passed to the Worker.
        Starts a 30-second timeout timer to prevent UI from freezing indefinitely.
        """
        self.thumbnail_operation_in_progress.emit(True)
        self._thumbnail_op_timed_out = False
        self._thumbnail_op_timer.start()

        # Pass the function and its arguments separately to the worker
        worker = Worker(service_function, *args)
        worker.signals.result.connect(result_slot)
        worker.signals.error.connect(self._on_thumbnail_operation_error)

        thread_pool = QThreadPool.globalInstance()
        if thread_pool:
            thread_pool.start(worker)
        else:
            logger.error("QThreadPool.globalInstance() is None. Cannot start worker.")
            self._thumbnail_op_timer.stop()
            self.thumbnail_operation_in_progress.emit(False)

    # ---Public Slots (for UI Edit Tracking) ---

    # In app/viewmodels/preview_panel_vm.py, replace the thumbnail-related slots
    def _on_new_thumbnail_operation_finished(self, result: dict):
        """
        Handles the result from any thumbnail operation (add, remove, remove_all).
        """
        self._thumbnail_op_timer.stop()
        if self._thumbnail_op_timed_out:
            logger.warning("Thumbnail operation finished but already timed out. Ignoring result.")
            return
        self.thumbnail_operation_in_progress.emit(False)  # Hide loading indicator

        if not result.get("success"):
            error_msg = result.get("error", _i18n.tr("vm.unknown_error"))
            self.toast_requested.emit(error_msg, "error")
            return

        # On success, get the new updated model from the result
        new_item_model = result.get("data")
        if not new_item_model:
            logger.error("Thumbnail operation succeeded but returned no data.")
            return

        # 1. Update this ViewModel's own state
        self.current_item_model = new_item_model

        # 2. Refresh the PreviewPanel UI itself
        self.toast_requested.emit(_i18n.tr("vm.thumb_updated"), "success")
        if isinstance(self.current_item_model, FolderItem):
            self.item_loaded.emit(self._create_dict_from_item(self.current_item_model))
        else:
            self.item_loaded.emit(None)

        # 3. START THE DOMINO EFFECT: Notify other parts of the app
        self.item_metadata_saved.emit(self.current_item_model)

    # Add this new slot for handling unexpected worker errors
    def _on_thumbnail_operation_error(self, error_info: tuple):
        """Handles unexpected errors from the thumbnail worker thread."""
        self._thumbnail_op_timer.stop()
        self.thumbnail_operation_in_progress.emit(False)
        logger.error(
            f"A critical error occurred in the thumbnail worker: {error_info[1]}",
            exc_info=error_info,
        )
        self.toast_requested.emit(
            _i18n.tr("vm.thumb_unexpected_error"), "error"
        )

    def _on_thumbnail_operation_timeout(self):
        """Handles the 30-second timeout for thumbnail operations.

        Resets the loading state and shows an error toast so the UI
        can recover even if a background worker hangs indefinitely.
        """
        if self._thumbnail_op_timed_out:
            return
        self._thumbnail_op_timed_out = True
        self.thumbnail_operation_in_progress.emit(False)
        logger.error("Thumbnail operation timed out after 30 seconds.")
        self.toast_requested.emit(
            _i18n.tr("vm.thumb_timeout"), "error"
        )

    def on_description_changed(self, text: str):
        """Flow 5.2 Part B: Tracks live edits in the description text area."""
        if not self.current_item_model:
            return

        # Compare the current text with the original description of the model
        current_description = (self.current_item_model.description or "").replace("\r\n", "\n")
        is_now_dirty = text != current_description

        # Only update and sign signal if the state 'is_description_dirty' changes
        if is_now_dirty != self.is_description_dirty:
            self.is_description_dirty = is_now_dirty
            self.is_description_dirty_changed.emit(self.is_description_dirty)

        # Save text that has not been stored if 'dirty'
        if self.is_description_dirty:
            self._unsaved_description = text
        else:
            self._unsaved_description = None

    def on_keybinding_edited(
        self, binding_id: str, field_type: str, field_identifier: object, new_value: str
    ):
        """
        Flow 5.2 Part D: Tracks live edits made to a keybinding in the UI.
        This version correctly handles the signal and data structure.
        """
        logger.debug(
            f"Keybinding edited: id={binding_id}, type={field_type}, identifier={field_identifier}, value='{new_value}'"
        )

        binding = next(
            (kb for kb in self.editable_keybindings if kb.binding_id == binding_id),
            None,
        )
        if binding is None:
            logger.warning(
                f"Ignoring edit for unknown keybinding id={binding_id}, type={field_type}"
            )
            return

        # Use Setdefault to make a sub-time if not yet. This is safer.
        changes_for_binding = self._unsaved_ini_changes.setdefault(binding_id, {})

        # Keep changes based on the type of field
        if field_type in ["key", "back"]:
            values = binding.keys if field_type == "key" else binding.backs
            if not isinstance(field_identifier, int) or not (
                0 <= field_identifier < len(values)
            ):
                logger.warning(
                    f"Ignoring {field_type} edit with invalid index={field_identifier} "
                    f"for keybinding id={binding_id}"
                )
                return

            values[field_identifier] = new_value

            # 'keys' and 'backs' stored in their own sub-dam
            key_or_back_changes = changes_for_binding.setdefault(field_type, {})
            # Field identifier here is an index (int)
            key_or_back_changes[field_identifier] = new_value

        elif field_type == "assignment":
            assignment = next(
                (a for a in binding.assignments if a.variable == field_identifier),
                None,
            )
            if assignment is None:
                logger.warning(
                    f"Ignoring assignment edit for unknown variable={field_identifier} "
                    f"on keybinding id={binding_id}"
                )
                return

            assignment.current_value = new_value

            # 'Assignments' is kept in its own sub-fiery
            assignment_changes = changes_for_binding.setdefault("assignments", {})
            # Field_Identifier here is the name of the variable (STR)
            assignment_changes[field_identifier] = new_value
        elif field_type == "note":
            binding.note = new_value
            self._notes_dirty = True
        else:
            logger.warning(
                f"Ignoring edit with unsupported field type={field_type} "
                f"for keybinding id={binding_id}"
            )
            return

        # Tell UI that there is a change in configuration. This has not been saved
        if not self.is_ini_dirty:
            self.is_ini_dirty = True
            self.ini_dirty_state_changed.emit(True)

    # ---Private/Internal Logic & Slots ---
    def open_ini_file(self, file_path: Path):
        """Requests the system utility to open the specified .ini file."""
        logger.info(f"Request to open .ini file:{file_path}")
        self.sys_utils.open_path_in_explorer(file_path)

    def _load_ini_config_async(self):
        """Flow 5.2 Part A: Starts the background worker to parse .ini files."""
        pass

    def _update_dirty_state(self):
        """Checks all unsaved flags and emits is_description_dirty_changed signal."""
        pass

    # ---Private Slots for Async Results ---
    def save_ini_config(self):
        """Starting the configuration storage process. This is in the background."""
        has_ini_changes = bool(self._unsaved_ini_changes)
        has_note_changes = self._notes_dirty

        if not has_ini_changes and not has_note_changes:
            return

        logger.info("Saving .ini configuration changes...")

        if has_ini_changes:
            worker = Worker(
                self.ini_parsing_service.save_ini_changes, self.editable_keybindings
            )
            worker.signals.result.connect(self._on_ini_saved)
            thread_pool = QThreadPool.globalInstance()
            if thread_pool:
                thread_pool.start(worker)
        else:
            # Notes-only: save directly instead of routing through INI callback
            self._save_notes()
            self._notes_dirty = False
            self.ini_dirty_state_changed.emit(False)

    def _on_ini_config_loaded(self, result: dict):
        """Handles the result of the .ini parsing worker."""
        self.ini_config_loading.emit(False)  # Hide Loading Spinner

        if result.get("success"):
            self.editable_keybindings = result.get("data", [])
            # Fill notes from _emm_notes.json
            if self.current_item_model and self.note_service:
                self._fill_notes_from_file()
            # Save the original state for comparison when there is editing
            self.original_keybindings = copy.deepcopy(self.editable_keybindings)

            # Populate INI cache
            if self.current_item_model:
                folder_path = self.current_item_model.folder_path
                ini_mtimes = [
                    p.stat().st_mtime
                    for p in folder_path.rglob("*.ini")
                    if p.is_file()
                ]
                current_max_mtime = max(ini_mtimes) if ini_mtimes else 0.0
                self._ini_cache[self.current_item_model.id] = (
                    self.editable_keybindings,
                    current_max_mtime,
                )

        self.ini_config_ready.emit(self.editable_keybindings)
        self.ini_dirty_state_changed.emit(False)

    def _on_ini_config_error(self, error_info: tuple):
        """Handling unexpected errors from Worker Parsing. This."""
        self.ini_config_loading.emit(False)
        logger.error(f"Critical error during .ini parsing:{error_info[1]}")
        self.toast_requested.emit(
            _i18n.tr("vm.ini_parse_critical"), "error"
        )
        self.ini_config_ready.emit([])  # Send an empty list

    # ── notes helpers ───────────────────────────────────────────────────────

    def _fill_notes_from_file(self) -> None:
        """Load notes from _emm_notes.json and populate each KeyBinding."""
        if not self.current_item_model:
            return
        notes = self.note_service.load_notes(self.current_item_model.folder_path)
        if not notes:
            return
        for kb in self.editable_keybindings:
            key = kb.note_key(self.current_item_model.folder_path)
            kb.note = notes.get(key, "")

    def _flush_notes(self) -> None:
        """Write all current KeyBinding notes to _emm_notes.json."""
        if not self.current_item_model:
            return
        notes = {}
        for kb in self.editable_keybindings:
            if kb.note:
                key = kb.note_key(self.current_item_model.folder_path)
                notes[key] = kb.note
        self.note_service.save_notes(self.current_item_model.folder_path, notes)

    def _save_notes(self) -> bool:
        """Persist notes to _emm_notes.json. Returns True on success."""
        if not self.current_item_model or not self.note_service:
            return False
        try:
            self._flush_notes()
            return True
        except Exception as e:
            logger.error("Failed to save notes: %s", e)
            self.toast_requested.emit(_i18n.tr("vm.failed_save_notes"), "error")
            return False

    def _on_description_saved(self, result: dict):
        """Handles the result of the description save operation."""
        if not result.get("success"):
            self.toast_requested.emit(result.get("error", _i18n.tr("vm.failed_save")), "error")
            return

        self.toast_requested.emit(_i18n.tr("vm.desc_saved"), "success")
        self._reset_dirty_state()

        # Update State with a new model from the safety results
        self.current_item_model = result.get("data")

        # Send a signal that metadata item has changed (for sync with foldergrid)
        self.item_metadata_saved.emit(self.current_item_model)

    def toggle_current_item_status(self, is_enabled: bool):
        """
        Starts the background process to toggle the enable/disable status
        of the currently displayed mod.
        """
        if not self.current_item_model:
            self.toast_requested.emit(_i18n.tr("vm.no_mod_toggle"), "warning")
            return

        logger.info(
            f"Toggling status for '{self.current_item_model.actual_name}' to {is_enabled}"
        )

        # Determine the target status for the service function
        target_status = ModStatus.ENABLED if is_enabled else ModStatus.DISABLED

        # Reuse the generic worker starter to run ModService.toggle_status
        # Note: You might need to adapt your _start_thumbnail_operation helper or
        # create a new one for generic operations. For clarity, we'll write it out here.
        worker = Worker(
            self.mod_service.toggle_status, self.current_item_model, target_status
        )
        worker.signals.result.connect(self._on_status_toggle_finished)
        worker.signals.error.connect(
            self._on_thumbnail_operation_error
        )  # Can reuse the generic error handler

        thread_pool = QThreadPool.globalInstance()
        if thread_pool:
            thread_pool.start(worker)

    # --- Add this new private slot ---
    def _on_status_toggle_finished(self, result: dict):
        """
        Handles the result of the toggle operation and triggers the domino effect.
        """
        if not result.get("success"):
            error_msg = result.get("error", _i18n.tr("vm.toggle_failed"))
            self.toast_requested.emit(error_msg, "error")

            # Revert the switch in the UI if the operation failed
            if self.current_item_model:
                self.item_loaded.emit(
                    self._create_dict_from_item(self.current_item_model)
                )
            return

        new_item_model = result.get("data")
        if not new_item_model:
            logger.error("Toggle operation succeeded but returned no data.")
            return

        # Update this ViewModel's own state
        self.current_item_model = new_item_model

        # Refresh the PreviewPanel UI itself to ensure consistency
        if self.current_item_model:
            self.item_loaded.emit(self._create_dict_from_item(self.current_item_model))

        # START THE DOMINO EFFECT to update the foldergrid
        self.toast_requested.emit(_i18n.tr("vm.status_updated"), "success")
        self.item_metadata_saved.emit(self.current_item_model)

    def _reset_dirty_state(self):
        self.is_description_dirty = False
        self._unsaved_description = None
        self.is_description_dirty_changed.emit(False)

        self.is_ini_dirty = False
        self._unsaved_ini_changes = {}
        self._notes_dirty = False
        self.ini_dirty_state_changed.emit(False)

    def _on_ini_saved(self, result: dict):
        """Handles the result of the .ini configuration save operation."""
        if not result.get("success"):
            errors = result.get("errors", [])
            error_msg = _i18n.tr("vm.ini_save_failed", count=len(errors))
            self.toast_requested.emit(error_msg, "error")
            return

        # Persist notes if dirty
        if self._notes_dirty:
            self._save_notes()

        self.toast_requested.emit(_i18n.tr("vm.config_saved"), "success")
        # After successfully saved, update State 'Original' and Reset 'Dirty' Flag
        self.original_keybindings = copy.deepcopy(self.editable_keybindings)
        self._unsaved_ini_changes = {}
        self._notes_dirty = False
        self.ini_dirty_state_changed.emit(False)

        # Invalidate INI cache so next load re-parses fresh data
        if self.current_item_model:
            self._ini_cache.pop(self.current_item_model.id, None)

    def _on_thumbnail_added(self, result: dict):
        """Handles the result of the thumbnail addition operation."""
        pass

    def _on_thumbnail_operation_complete(self, result: dict):
        """
        Handles the result from ANY thumbnail operation.
        Processes the result, invalidates cache, and triggers all necessary UI updates.
        """
        self._thumbnail_op_timer.stop()
        if self._thumbnail_op_timed_out:
            logger.warning(
                "Thumbnail operation finished but already timed out. Ignoring result."
            )
            return
        self.thumbnail_operation_in_progress.emit(False)

        if not result.get("success"):
            error_msg = result.get("error", _i18n.tr("vm.unknown_error"))
            self.toast_requested.emit(error_msg, "error")
            return

        new_item_model = result.get("data")
        if not new_item_model:
            logger.error("Thumbnail operation succeeded but returned no data.")
            return

        # Invalidate cache for any deleted images
        deleted_paths = result.get("deleted_paths", [])
        if deleted_paths:
            logger.info(
                f"Invalidating cache for {len(deleted_paths)} deleted thumbnails."
            )
            for path in deleted_paths:
                self.thumbnail_service.invalidate_cache(
                    new_item_model.id, path
                )

        # Show warning toast if fallback (permanent) deletion was used
        fallback_warnings = result.get("fallback_warnings", [])
        if fallback_warnings:
            self.toast_requested.emit(
                _i18n.tr("vm.perm_deleted_warn", count=len(fallback_warnings)),
                "warning"
            )

        # Update state and refresh UI
        self.current_item_model = new_item_model

        # Always invalidate cache so the grid thumbnail regenerates
        # from the updated preview_images[0]. This specifically covers
        # reorder/set-as-cover operations that don't produce deleted_paths.
        # For add/remove flows the extra invalidation is harmless.
        self.thumbnail_service.invalidate_cache(self.current_item_model.id)

        self.toast_requested.emit(_i18n.tr("vm.thumb_updated"), "success")
        if isinstance(self.current_item_model, FolderItem):
            self.item_loaded.emit(self._create_dict_from_item(self.current_item_model))
        else:
            self.item_loaded.emit(None)
        self.item_metadata_saved.emit(self.current_item_model)

    def paste_thumbnail_from_clipboard(self):
        """
        Gets an image from the clipboard via ImageUtils and initiates the add thumbnail process.
        """
        # The ViewModel calls the utility layer to get the data
        image_data = self.image_utils.get_image_from_clipboard()

        if image_data:
            self.add_new_thumbnail(image_data)
        else:
            self.toast_requested.emit(_i18n.tr("vm.no_clipboard"), "warning")

    def set_preview_image_as_cover(self, image_path: Path):
        """Moves the specified image to index 0 so it becomes the mod cover."""
        if not self.current_item_model or not image_path:
            return

        old_list = list(self.current_item_model.preview_images)
        if image_path not in old_list or old_list.index(image_path) == 0:
            return

        # Move the target image to the front
        new_list = [image_path] + [p for p in old_list if p != image_path]

        logger.info(
            f"Setting '{image_path.name}' as cover for '{self.current_item_model.actual_name}'"
        )
        self.thumbnail_operation_in_progress.emit(True)

        worker = Worker(
            self.mod_service.reorder_preview_images,
            self.current_item_model,
            new_list,
        )
        worker.signals.result.connect(self._on_thumbnail_operation_complete)
        worker.signals.error.connect(self._on_thumbnail_operation_error)
        QThreadPool.globalInstance().start(worker)

    def _flush_pending_changes_sync(self):
        """Synchronously persist all pending edits. No-op if nothing is loaded."""
        if self.current_item_model is None:
            return
        try:
            if self.is_description_dirty and self._unsaved_description is not None:
                try:
                    self.mod_service.update_item_properties(
                        self.current_item_model, {"description": self._unsaved_description}
                    )
                    self.is_description_dirty = False
                    self._unsaved_description = None
                    self.is_description_dirty_changed.emit(False)
                except Exception as e:
                    logger.error("Failed to save description in sync flush: %s", e)
                    self.toast_requested.emit(
                        _i18n.tr("vm.failed_save"), "error"
                    )
            if self.is_ini_dirty:
                try:
                    self.ini_parsing_service.save_ini_changes(self.editable_keybindings)
                    if self.current_item_model:
                        self._ini_cache.pop(self.current_item_model.id, None)
                    self._unsaved_ini_changes = {}
                    self.is_ini_dirty = False
                    self.ini_dirty_state_changed.emit(False)
                except Exception as e:
                    logger.error("Failed to save ini config in sync flush: %s", e)
                    self.toast_requested.emit(
                        _i18n.tr("vm.ini_save_failed", count=1), "error"
                    )
            if self._notes_dirty:
                self._save_notes()
                self._notes_dirty = False
        except Exception as e:
            logger.error("Unexpected error in sync flush: %s", e)

    def clear_panel(self):
        "" "Clean the preview panel." ""
        logger.info("Clearing Preview Panel.")
        if self.current_item_model is None:
            return  # Already cleared, do nothing.
        # Reset all internal state
        self.current_item_model = None
        self.editable_keybindings = []

        # Reset dirty flags to hide save buttons
        self._reset_dirty_state()

        # Emit signal with None to tell the View to show its null state page
        self.item_loaded.emit(None)
