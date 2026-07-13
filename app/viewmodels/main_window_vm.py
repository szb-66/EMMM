# App/viewmodels/main window vm.py

import os
from pathlib import Path
import subprocess
from PyQt6.QtCore import QObject, pyqtSignal, QThreadPool, QTimer
from typing import Optional, List, Dict
import subprocess as sp
from app.utils.logger_utils import logger
from app.utils.async_utils import Worker
from app.models.mod_item_model import ModType
# Import models and services for type hinting

from app.models.config_model import AppConfig
from app.models.game_model import Game
from app.models.mod_item_model import ObjectItem
from app.services.config_service import ConfigService
from app.services.file_watcher_service import FileWatcherService
from app.services.workflow_service import WorkflowService
from .mod_list_vm import ModListViewModel
from .preview_panel_vm import PreviewPanelViewModel

from enum import Enum, auto


class ToastLevel(Enum):
    INFO = auto()
    SUCCESS = auto()
    WARNING = auto()
    ERROR = auto()


class MainWindowViewModel(QObject):
    """
    Orchestrates high-level application state, global workflows,
    and communication between other ViewModels.
    """

    # ---Signals for Global UI Feedback ---
    toast_requested = pyqtSignal(str, ToastLevel)  # message, level

    global_operation_started = pyqtSignal(str)
    global_operation_finished = pyqtSignal()
    global_progress_updated = pyqtSignal(int, int)  # value, total

    settings_dialog_requested = pyqtSignal()
    safe_mode_switch_state = pyqtSignal(bool)

    # ---Signals for Game List UI ---
    game_list_updated = pyqtSignal(list)  # list[dict] instead of list[Game]
    active_game_changed = pyqtSignal(object)  # Game object or None
    category_switch_requested = pyqtSignal(str) # 'character' or 'other'
    play_settings_required = pyqtSignal()
    play_button_state_changed = pyqtSignal(bool)
    bulk_progress_updated = pyqtSignal(int, int)

    def __init__(
        self,
        config_service: ConfigService,
        workflow_service: WorkflowService,
        objectlist_vm: ModListViewModel,
        foldergrid_vm: ModListViewModel,
        preview_panel_vm: PreviewPanelViewModel,
    ):
        super().__init__()

        # ---Injected Services & ViewModels ---
        self.config_service = config_service
        self.workflow_service = workflow_service
        self.objectlist_vm = objectlist_vm
        self.foldergrid_vm = foldergrid_vm
        self.preview_panel_vm = preview_panel_vm

        # ---Internal State ---
        self.config: Optional[AppConfig] = None
        self.active_game: Optional[Game] = None
        self.active_object: Optional[ObjectItem] = None
        self._pending_foldergrid_path_to_refresh: Path | None = None
        self._file_watcher = FileWatcherService()
        self._watch_debounce_timers: dict[str, QTimer] = {}
        self._watch_suppression_tokens: dict[str, int] = {}
        self._file_watcher.directory_changed.connect(self._on_watched_directory_changed)

        # Ignore internal metadata / content writes so they don't trigger
        # full list refreshes.  List structure only changes on folder-level
        # events (create / delete / rename), not file-level writes.
        self._file_watcher.ignore_patterns(
            "objectlist",
            ["**/info.json", "**/properties.json", "**/_thumb.*",
             "**/preview*.*", "**/*.ini"],
        )
        self._file_watcher.ignore_patterns(
            "foldergrid",
            ["**/info.json", "**/properties.json", "**/_thumb.*",
             "**/preview*.*", "**/*.ini"],
        )
        self._connect_child_vm_signals()

    # ---Initialization ---

    def start_initial_load(self):
        """Flow 1.1: Kicks off the application loading sequence in a background thread."""
        logger.info("Starting initial configuration load...")
        self.toast_requested.emit("Loading configuration...", ToastLevel.INFO)

        # Create a worker to load config file without blocking the UI
        worker = Worker(self.config_service.load_config)

        # Connect signals from the worker to the appropriate slots
        worker.signals.result.connect(self._on_load_config_finished)
        worker.signals.error.connect(self._on_load_config_error)

        # Execute the worker in the global thread pool
        thread_pool = QThreadPool.globalInstance()

        if thread_pool:
            thread_pool.start(worker)
        else:
            # This case is highly unlikely in a running app but is good to handle.
            logger.critical("Could not retrieve the global QThreadPool instance.")
            self.toast_requested.emit(
                "Critical error: Could not start background tasks.", "error"
            )

    def refresh_all_from_config(self):
        """
        [REVISED] Reloads config from disk and ensures all child VMs
        are updated with the new, refreshed game object references.
        """
        logger.info("Configuration has changed. Refreshing application state...")

        # 1. Keep track of the previously active game's ID
        previous_active_game_id = self.active_game.id if self.active_game else None

        # 2. Load the new config from the file
        new_config = self.config_service.load_config()

        # 3. Update the main list of games
        self._on_load_config_finished(new_config)

        # 4. Find the corresponding refreshed game object and RESET the active game
        if previous_active_game_id:
            refreshed_active_game = next(
                (g for g in self.config.games if g.id == previous_active_game_id), None
            )

            if refreshed_active_game:
                # Update the active game reference in this ViewModel
                self.active_game = refreshed_active_game

                logger.info(f"Forcing objectlist refresh for game '{refreshed_active_game.name}' with new game_type '{refreshed_active_game.game_type}'.")
                self.objectlist_vm.load_items(
                    path=refreshed_active_game.path,
                    game=refreshed_active_game,
                    is_new_root=True # Treat this as a root change to reset filters etc.
                )
                # ---------------------
            else:
                # The previously active game was deleted, clear the view
                self.set_current_game(None)

    def run_auto_play_on_startup(self):
        """
        Checks the config and runs the launcher if auto-play is enabled.
        This should be called once after the initial config is loaded.
        """
        logger.info("Checking for auto-play on startup...")
        if self.config and self.config.auto_play_on_startup and self.config.launcher_path:
            launcher_path = Path(self.config.launcher_path)
            if launcher_path.is_file():
                logger.info(f"Auto-play is enabled. Attempting to run: {launcher_path}")
                self.on_play_button_clicked()
            else:
                logger.warning("Auto-play enabled, but launcher path is invalid.")

    # ---Public Slots (for UI Actions) ---

    def set_current_game(self, game: Optional[Game]):
        """Flow 2.1: Sets the active game, triggering objectlist load."""
        if not game:
            self.active_game = None
            self.active_object = None
            self._file_watcher.clear_watch("objectlist")
            self._file_watcher.clear_watch("foldergrid")
            self.objectlist_vm.unload_items()
            self.foldergrid_vm.unload_items()
            self.preview_panel_vm.clear_panel()
            self.active_game_changed.emit(None)
            return

        if self.active_game and self.active_game.id == game.id:
            return  # Do nothing if the game is the same or invalid

        logger.info(f"Setting active game to: '{game.name}'")
        self.active_game = game

        # Save this choice for the next session
        self.config_service.save_setting("last_active_game_id", self.active_game.id)

        # Revised: DICT EMIT contains relevant data, not all objects
        active_game_data = {"name": self.active_game.name, "id": self.active_game.id}
        self.active_game_changed.emit(active_game_data)

        # Flow 2.1 Step 5: Trigger the next flow
        if self.active_game.path and self.active_game.path.is_dir():
            self._file_watcher.watch_directory("objectlist", self.active_game.path)
            self.objectlist_vm.load_items(
                path=self.active_game.path, game=self.active_game
            )
        else:
            self._file_watcher.clear_watch("objectlist")
            logger.error(
                f"Cannot load mods for '{self.active_game.name}', path is invalid or not set."
            )
            self.objectlist_vm.unload_items()
            self.foldergrid_vm.unload_items()
            self.toast_requested.emit(
                f"Path for {self.active_game.name} is invalid!", "error"
            )

    def set_current_game_by_name(self, game_name: str):
        """
        Finds a game by its name and sets it as active.
        Called by the UI (e.g., ComboBox).
        """
        if not self.config:
            return

        game = next((g for g in self.config.games if g.name == game_name), None)
        if game:
            self.set_current_game(game)

    def set_active_object(self, object_item_data: dict | None):
        """
        Flow 2.3 Trigger A: Receives a data dictionary from the view, finds the
        corresponding model object, and triggers the foldergrid load.
        """
        if not object_item_data:
            self.active_object = None
            if self.foldergrid_vm:
                self.foldergrid_vm.unload_items()
            return

        item_id = object_item_data.get("id")
        if not item_id:
            logger.error("set_active_object received data with no ID.")
            return

        # Redundancy Prevention: Check against the current active object's ID

        if self.active_object and self.active_object.id == item_id:
            return

        # ---LOGIC: Find the actual model object from the list ---

        object_item = next(
            (item for item in self.objectlist_vm.master_list if item.id == item_id),
            None,
        )

        if not object_item:
            logger.error(
                f"Could not find ObjectItem with ID '{item_id}' in master list."
            )
            return
        # ---END REVISED LOGIC ---

        # From here on, we use the real `object_item` model, so the rest of the code works.

        logger.info(f"Setting active object to: '{object_item.actual_name}'")
        self.active_object = object_item

        if self.active_game and object_item.folder_path.is_dir():
            self._file_watcher.watch_directory("foldergrid", object_item.folder_path)
            self.foldergrid_vm.load_items(
                path=object_item.folder_path, game=self.active_game, is_new_root=True
            )
        elif not self.active_game:
            logger.error("Cannot load foldergrid: No active game context.")
        else:
            logger.error(
                f"Path for object '{object_item.actual_name}' is invalid: {object_item.folder_path}"
            )
            self._file_watcher.clear_watch("foldergrid")
            self.foldergrid_vm.unload_items()
            self.toast_requested.emit(
                f"Path for {object_item.actual_name} is invalid!", "error"
            )

    def toggle_safe_mode(self, is_on: bool):
        """Flow 6.1: Initiates the global Safe Mode workflow."""
        pass  # Validates, then starts async worker to call workflow_service.apply_safe_mode()

    def initiate_global_randomize(self):
        """Flow 6.2.B: Initiates the global mod randomization workflow."""
        pass  # Validates, gets user confirmation, then starts async worker for global randomize.

    def request_main_refresh(self):
        """Handles the main refresh button action, reloading the active view."""
        if self.active_game:
            # Store the path we want to recover after the objectlist is refreshed
            if self.active_object and self.foldergrid_vm.current_path:
                self._pending_foldergrid_path_to_refresh = (
                    self.foldergrid_vm.current_path
                )
            else:
                self._pending_foldergrid_path_to_refresh = None

            # 1. Always refresh the top-level object list
            logger.info(f"Refreshing object list for '{self.active_game.name}'")
            self.objectlist_vm.load_items(
                path=self.active_game.path,
                game=self.active_game,
                is_new_root=True,  # Treat refresh as setting a new root
            )

        else:
            logger.warning("Refresh requested, but no active game.")
            self.toast_requested.emit("No active game to refresh.", "info")

    # ---Private Slots (for Async/Signal Handling) ---

    def _connect_child_vm_signals(self):
        """Connects signals from child VMs to orchestrator methods."""
        self.objectlist_vm.object_created.connect(self._on_object_created)
        self.objectlist_vm.list_refresh_requested.connect(self._on_list_refresh_requested)
        self.foldergrid_vm.list_refresh_requested.connect(self._on_list_refresh_requested)
        self.objectlist_vm.watched_refresh_suppression_requested.connect(
            self._suppress_watched_refresh
        )
        self.foldergrid_vm.watched_refresh_suppression_requested.connect(
            self._suppress_watched_refresh
        )
        self.objectlist_vm.reconciliation_progress_updated.connect(self.bulk_progress_updated)
        # Flow 3.1a & 4.2.A: An active object was modified/renamed
        self.objectlist_vm.active_object_modified.connect(
            self._on_active_object_modified
        )
        # Flow 4.2.B: An active object was deleted
        self.objectlist_vm.active_object_deleted.connect(self._on_active_object_deleted)

        # Flow 3.1b: A foldergrid item was modified, check if it's the one in preview
        self.foldergrid_vm.foldergrid_item_modified.connect(
            self._on_foldergrid_item_modified
        )

        # Flow 2.3 Trigger B: An item in the object list was selected
        self.preview_panel_vm.item_metadata_saved.connect(
            self.foldergrid_vm.update_item_in_list
        )
        self.objectlist_vm.load_completed.connect(self._on_objectlist_refresh_complete)
        self.objectlist_vm.toast_requested.connect(self._on_toast_requested)
        self.foldergrid_vm.toast_requested.connect(self._on_toast_requested)
        self.preview_panel_vm.toast_requested.connect(self._on_toast_requested)
        self.foldergrid_vm.active_selection_changed.connect(
            self._on_foldergrid_selection_changed
        )
        self.foldergrid_vm.selection_invalidated.connect(
            self.preview_panel_vm.clear_panel
        )
        self.objectlist_vm.selection_invalidated.connect(
            self._on_active_object_invalidated
        )
        self.foldergrid_vm.path_changed.connect(self._on_foldergrid_path_changed)

        # Cross-VM DnD: a mod was dragged from foldergrid onto a character row.
        self.objectlist_vm.move_to_character_requested.connect(
            self._on_move_to_character_requested
        )

    def _on_toast_requested(self, message: str, level: str = "info"):
        """
        Creates and shows a non-blocking InfoBar (toast) notification
        at the top-right of the window.
        """
        # Convert string level to ToastLevel enum if necessary
        if isinstance(level, str):
            try:
                toast_level = ToastLevel[level.upper()]
            except KeyError:
                toast_level = ToastLevel.INFO
        else:
            toast_level = level
        # Emit the toast notification
        self.toast_requested.emit(message, toast_level)

    def _on_active_object_modified(self, new_object_item: ObjectItem):
        """
        Handles the domino effect when an active object is modified (e.g., toggled).
        """
        self._suppress_watched_refresh("objectlist")

        # Check whether the item that changes is the item that we are actively seeing.

        if self.active_object and self.active_object.id == new_object_item.id:
            logger.info(
                f"Active object '{self.active_object.actual_name}' was modified. Refreshing foldergrid."
            )

            # 1. Update the active object reference in the main view model
            self.active_object = new_object_item

            # 1b. Guard against reload collision: if the foldergrid is still
            #     mid-operation (toggle/pin/rename worker in flight, or a load
            #     already queued), defer the reload by a short timer so the
            #     widget being processed is not replaced/deleted underneath us.
            #     This prevents the "toggle a mod → foldergrid reloads →
            #     processing animation lands on a deleted widget → crash"
            #     chain observed when rapid-toggling objectlist items.
            fg_vm = self.foldergrid_vm
            if fg_vm._processing_ids:
                logger.debug(
                    "Deferring foldergrid reload: processing_ids non-empty."
                )
                QTimer.singleShot(
                    300,
                    lambda: self._on_active_object_modified(new_object_item),
                )
                return

            # 1c. If the foldergrid is already displaying the (now updated)
            #     path, an identical reload is redundant and would just rebuild
            #     the widget tree for nothing — skip it.
            current_path = getattr(fg_vm, "current_path", None)
            if (
                current_path is not None
                and new_object_item.folder_path is not None
                and Path(current_path) == Path(new_object_item.folder_path)
            ):
                logger.debug(
                    "Skipping redundant foldergrid reload — path unchanged."
                )
                return

            # 2. Reload foldergrid with the (possibly renamed) new path.
            self.foldergrid_vm.load_items(
                path=new_object_item.folder_path,
                game=self.active_game,
                is_new_root=True,
            )

    def _on_active_object_deleted(self, deleted_item_id: str):
        """
        [IMPLEMENTED] Handles the domino effect when the currently active
        object is deleted from the objectlist.
        """
        # Check if the deleted item is the one currently active
        if self.active_object and self.active_object.id == deleted_item_id:
            logger.info(f"Active object '{self.active_object.actual_name}' was deleted. Clearing dependent views.")

            # 1. Clear active object state
            self.active_object = None

            # 2. Instruct foldergrid and preview_panel to clear themselves
            self._file_watcher.clear_watch("foldergrid")
            self.foldergrid_vm.unload_items()
            self.preview_panel_vm.clear_panel()

    def _on_active_object_invalidated(self):
        """Clears dependent views when the selected object no longer exists."""
        if not self.active_object:
            return

        logger.info(
            f"Active object '{self.active_object.actual_name}' no longer exists. Clearing dependent views."
        )
        self.active_object = None
        self._file_watcher.clear_watch("foldergrid")
        self.foldergrid_vm.unload_items()
        self.preview_panel_vm.clear_panel()

    def _process_config_update(self):
        """
        Flow 2.1 Step 2: Core function for processing configuration updates.
        """
        if not self.config or not self.config.games:
            logger.warning(
                "No games configured. Unloading content and requesting settings dialog."
            )
            self.objectlist_vm.unload_items()
            self.foldergrid_vm.unload_items()
            self.active_game_changed.emit(None)  # Notify UI to disable relevant parts

            self.settings_dialog_requested.emit()
            return

        # Convert Game objects to dictionaries

        view_data = [{"name": g.name, "id": g.id} for g in self.config.games]

        self.game_list_updated.emit(view_data)  # Emit list of dictionaries

        self._determine_active_game()

    def _determine_active_game(self):
        """Flow 2.1 Step 4: Finds the last active game or defaults to the first."""
        if not self.config:
            return

        game_to_set = None
        previous_active_id = (
            self.active_game.id if self.active_game else self.config.last_active_game_id
        )

        if previous_active_id:
            game_to_set = next(
                (g for g in self.config.games if g.id == previous_active_id), None
            )

        if not game_to_set:
            game_to_set = self.config.games[0]
            logger.info(
                f"No valid last active game found. Defaulting to first game: '{game_to_set.name}'"
            )

        self.set_current_game(game_to_set)

    def _on_load_config_finished(self, app_config: AppConfig):
        """
        Flow 1.1: Slot executed when the config is successfully loaded.
        It updates the state and triggers the next step in the loading process.
        """
        logger.info("Configuration loaded. Updating view model state...")
        self.config = app_config
        is_play_enabled = bool(app_config and app_config.launcher_path)
        self.play_button_state_changed.emit(is_play_enabled)

        # Proceed to the next step in the startup flow
        self._process_config_update()
        self.run_auto_play_on_startup()

    def _on_load_config_error(self, error_info: tuple):
        """Handles errors that occur during the config loading process."""
        exctype, value, tb = error_info
        logger.critical(
            f"An unhandled exception occurred during config load: {value}\n{tb}"
        )
        self.toast_requested.emit(
            "Error loading configuration. See logs for details.", ToastLevel.ERROR
        )
        # In case of a critical error, we can proceed with a default empty config

        self._on_load_config_finished(AppConfig())

    def _on_safe_mode_finished(self, result):
        """Flow 6.1: Handles the result of the Safe Mode workflow."""
        pass  # Hides overlay, saves config, and reloads foldergrid on success.

    def _on_foldergrid_item_modified(self, modified_item):
        """
        Flow 3.1b Domino Effect: Checks if the modified item from the grid
        is the one currently active in the PreviewPanel.
        """
        self._suppress_watched_refresh("foldergrid")

        # Check if the preview panel is displaying something and if the IDs match
        if (
            self.preview_panel_vm.current_item_model
            and self.preview_panel_vm.current_item_model.id == modified_item.id
        ):

            logger.info(
                f"Currently previewed item '{modified_item.actual_name}' was modified. Updating preview."
            )
            # If it matches, forward the updated model object to preview_panel_vm
            logger.info(
                f"Currently previewed item '{modified_item.actual_name}' was modified. Updating preview."
            )
            self.preview_panel_vm.update_view_for_item(modified_item)

    def _on_move_to_character_requested(self, item_id: str, target_character_path):
        """Cross-VM DnD: moves a mod from the current foldergrid into a character's root."""
        logger.info(f"Cross-VM move: item '{item_id}' → '{target_character_path}'")
        self.foldergrid_vm.move_item_to_folder(item_id, target_character_path)

    def _on_objectlist_refresh_complete(self, success: bool):
        """
        Handles the refresh chain. After the objectlist is refreshed,
        it intelligently decides whether to restore the foldergrid's sub-path
        or clear its selection.
        """
        path_to_recover = self._pending_foldergrid_path_to_refresh
        self._pending_foldergrid_path_to_refresh = (
            None  # Clear pending state immediately
        )

        if not success:
            return

        if self.active_object:
            refreshed_active_object = next(
                (
                    item
                    for item in self.objectlist_vm.master_list
                    if item.id == self.active_object.id
                ),
                None,
            )
            if not refreshed_active_object:
                refreshed_active_object = next(
                    (
                        item
                        for item in self.objectlist_vm.master_list
                        if item.actual_name == self.active_object.actual_name
                    ),
                    None,
                )
            if refreshed_active_object:
                self.active_object = refreshed_active_object
            else:
                self._on_active_object_invalidated()
                return

        if not path_to_recover:
            # Nothing to recover, we are done.
            return

        # After objectlist refresh, self.active_object is now up-to-date.
        # Check if the path to recover is still valid and belongs to the active object.
        is_path_still_valid = False
        if self.active_object and path_to_recover.is_dir():
            try:
                # This check ensures the path is still a child of the (potentially renamed) active object
                path_to_recover.relative_to(self.active_object.folder_path)
                is_path_still_valid = True
            except ValueError:
                is_path_still_valid = False

        if is_path_still_valid:
            # If path is valid, restore the foldergrid view to that path.
            logger.info(
                f"Step 2: Restoring and refreshing folder grid view for '{path_to_recover}'"
            )
            self.foldergrid_vm.load_items(
                path=path_to_recover, game=self.active_game, is_new_root=False
            )
        else:
            # --- FIX: If path is NOT valid, explicitly clear the foldergrid selection ---
            # This will trigger the domino effect to clear the PreviewPanel.
            logger.warning(
                f"Could not restore path '{path_to_recover}', it's no longer valid. Clearing selection."
            )
            self.foldergrid_vm.set_active_selection(None)
            if self.active_object and self.active_object.folder_path.is_dir():
                self.foldergrid_vm.load_items(
                    path=self.active_object.folder_path,
                    game=self.active_game,
                    is_new_root=True,
                )
            else:
                self.foldergrid_vm.unload_items()

    def _on_foldergrid_selection_changed(self, selected_item_id: str | None):
        """
        Handles when the active selection in the foldergrid is cleared.
        """
        # If the selection is cleared (ID is None), command the preview panel to clear itself.
        # We don't need to handle the case where an item IS selected, because that's
        # already handled by the item_selected -> set_current_item flow.
        if selected_item_id is None:
            logger.info(
                "Foldergrid selection cleared, commanding preview panel to clear."
            )
            self.preview_panel_vm.clear_panel()

    def _on_foldergrid_path_changed(self, new_path: Path | None):
        if new_path and new_path.is_dir():
            self._file_watcher.watch_directory("foldergrid", new_path)
        else:
            self._file_watcher.clear_watch("foldergrid")

    def _on_watched_directory_changed(self, key: str, changed_path: Path):
        logger.debug(f"Detected filesystem change for {key}: {changed_path}")

        if self._watch_suppression_tokens.get(key, 0):
            return

        timer = self._watch_debounce_timers.get(key)
        if not timer:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda key=key: self._refresh_watched_context(key))
            self._watch_debounce_timers[key] = timer

        timer.start(400)

    def _suppress_watched_refresh(self, key: str, duration_ms: int = 5000):
        """
        Temporarily ignores watcher refreshes caused by internal file operations.
        Single-item updates already patch the relevant widgets directly, so the
        follow-up watchdog event would only rebuild the list and cause flicker.
        """
        keys_to_suppress = [key]
        if key == "foldergrid":
            # Renaming a child folder also raises a change for the watched
            # objectlist directory on Windows, which otherwise reloads both panes.
            keys_to_suppress.append("objectlist")
        elif key == "objectlist":
            keys_to_suppress.append("foldergrid")

        for suppress_key in dict.fromkeys(keys_to_suppress):
            self._suppress_single_watched_refresh(suppress_key, duration_ms)

    def _suppress_single_watched_refresh(self, key: str, duration_ms: int):
        timer = self._watch_debounce_timers.get(key)
        if timer:
            timer.stop()

        self._file_watcher.suppress_watch(key, duration_ms)

        token = self._watch_suppression_tokens.get(key, 0) + 1
        self._watch_suppression_tokens[key] = token
        logger.debug(f"Suppressing watched refresh for {key}.")

        def clear_suppression():
            if self._watch_suppression_tokens.get(key) == token:
                self._watch_suppression_tokens.pop(key, None)
                logger.debug(f"Watched refresh suppression cleared for {key}.")

        QTimer.singleShot(duration_ms, clear_suppression)

    def _refresh_watched_context(self, key: str):
        if self._watch_suppression_tokens.get(key, 0):
            logger.debug(f"Skipping suppressed watched refresh for {key}.")
            return

        if key == "objectlist":
            if self.active_game and self.active_game.path.is_dir():
                logger.info("Refreshing object list after external filesystem change.")
                self.request_main_refresh()
            else:
                self.objectlist_vm.unload_items()
                self._on_active_object_invalidated()
            return

        if key == "foldergrid":
            if not self.active_game:
                return

            current_path = self.foldergrid_vm.current_path
            if current_path and current_path.is_dir():
                logger.info("Refreshing folder grid after external filesystem change.")
                self.foldergrid_vm.load_items(
                    path=current_path,
                    game=self.active_game,
                    is_new_root=(current_path == self.foldergrid_vm.navigation_root),
                )
            elif self.active_object and self.active_object.folder_path.is_dir():
                logger.info("Folder grid path is invalid. Falling back to active object root.")
                self.foldergrid_vm.load_items(
                    path=self.active_object.folder_path,
                    game=self.active_game,
                    is_new_root=True,
                )
            else:
                logger.info("Folder grid path and active object are invalid. Clearing dependent views.")
                self._on_active_object_invalidated()

    def shutdown(self):
        for timer in self._watch_debounce_timers.values():
            timer.stop()
        self._file_watcher.stop()

    def on_category_selected(self, category_key: str):
        """
        Called by the MainWindow when a category navigation item is clicked.
        Orchestrates the filtering of the object list.
        """
        # Convert the string key from the UI into a ModType enum
        category = ModType.CHARACTER if category_key == 'character' else ModType.OTHER

        # Delegate the actual filtering logic to the specialized ViewModel
        self.objectlist_vm.set_category_filter(category)

        # In Stage 3, this method will also be responsible for
        # triggering the update of the detailed filter UI.

    def _on_object_created(self, new_object_data: dict):
        """
        Receives a signal when a new object is created and decides
        which category sidebar to switch to.
        """
        object_type = new_object_data.get("object_type")
        if object_type == ModType.CHARACTER.value:
            self.category_switch_requested.emit("character")
        else:
            self.category_switch_requested.emit("other")

    def on_play_button_clicked(self):
        """
        Handles the logic when the main 'Play' button is clicked.
        """
        if self.config and self.config.launcher_path:
            launcher_path = Path(self.config.launcher_path)
            if launcher_path.is_file():
                logger.info(f"Play button clicked. Running: {launcher_path}")
                try:
                    subprocess.Popen([str(launcher_path)], cwd=str(launcher_path.parent))
                except OSError as e:
                    if e.winerror == 740:
                        logger.warning("Elevation required. Trying runas fallback...")
                        try:
                            logger.warning("Elevation needed. Fallback via PowerShell…")
                            ret = self.run_as_admin_with_powershell(str(launcher_path))
                            if ret != 0:
                                err = f"Powershell exit code {ret}"
                                logger.error(f"Fallback elevation failed: {err}")
                                self.toast_requested.emit(f"Failed to run as admin: {err}", ToastLevel.ERROR)

                        except Exception as fallback_error:
                            logger.error(f"Fallback elevation failed: {fallback_error}")
                            self.toast_requested.emit(f"Failed to run launcher (admin): {fallback_error}", ToastLevel.ERROR)
                    else:
                        logger.error(f"Failed to run launcher: {e}")
                        self.toast_requested.emit(f"Failed to run launcher: {e}", ToastLevel.ERROR)
                except Exception as e:
                    logger.error(f"Failed to run launcher: {e}")
                    self.toast_requested.emit(f"Failed to run launcher: {e}", "error")
            else:
                self.toast_requested.emit("Launcher path is invalid. Please check settings.", "warning")
                self.play_settings_required.emit()
        else:
            logger.info("Play button clicked, but no launcher path is set. Requesting settings.")
            self.play_settings_required.emit()

    @staticmethod
    def run_as_admin_with_powershell(cmd_path: str):
        ps_cmd = (
            f'powershell -Command "Start-Process \'{cmd_path}\' -Verb RunAs"'
        )
        return os.system(ps_cmd)

    def _on_list_refresh_requested(self):
        """
        Handles a request from a child ViewModel to reload the object list.
        This ensures the reload uses the most up-to-date game object.
        """
        sender_vm = self.sender()
        if sender_vm not in [self.objectlist_vm, self.foldergrid_vm]:
            return

        if self.active_game and self.active_game.path.is_dir():
            logger.info(f"Handling refresh request for '{sender_vm.context}' of game '{self.active_game.name}'.")

            # Use the most up-to-date path from the child VM, but the game object from this orchestrator
            path_to_load = sender_vm.current_path if sender_vm.current_path else self.active_game.path

            sender_vm.load_items(
                path=path_to_load,
                game=self.active_game, # Provide the master, up-to-date game object
                is_new_root=(sender_vm == self.objectlist_vm) # A full refresh of objectlist is a root change
            )
