# app/viewmodels/mod_list_vm/_load_mixin.py
"""Skeleton load + lazy hydration + skeleton-result handlers.

Extracted from the original monolithic `mod_list_vm.py` per ADR 0001.
The Mixin must NOT define `__init__` or any `pyqtSignal` — those stay
on the host `ModListViewModel` because pyqtSignal is a Qt descriptor that
must live on a `QObject` subclass.
"""
import dataclasses
from pathlib import Path

from PyQt6.QtCore import QThreadPool

from app.models.game_model import Game
from app.models.mod_item_model import (
    ModStatus,
    BaseModItem,
    ObjectItem,
    CharacterObjectItem,
    GenericObjectItem,
    FolderItem,
)
from app.utils.async_utils import Worker
from app.utils.logger_utils import logger
from app.core.constants import CONTEXT_OBJECTLIST, CONTEXT_FOLDERGRID


class _LoadMixin:
    # --- Loading, hydration, and skeleton/load result handlers ---
    def load_items(
        self, path: Path, game: Game | None = None, is_new_root: bool = False
    ):
        """
        Flow 2.2 & 2.3: Starts the two-stage loading process (Skeleton stage).
        This version is cleaned up to prevent item stacking and redundant signals.
        """
        if not path or not path.is_dir():
            self.toast_requested.emit(f"Invalid path provided: {path}", "error")
            return

        # 1. Race Condition Prevention
        self.current_load_token += 1
        token_for_this_load = self.current_load_token
        logger.info(f"Loading items for '{path}' with token {token_for_this_load}")

        # 2. Reset Internal State
        self.master_list = []
        self.displayed_items = []
        self.current_path = path
        self.current_game = game
        if is_new_root:
            self.navigation_root = path

        self.loading_started.emit()

        # Update breadcrumb path after starting the loading state
        if self.context == "foldergrid":
            self.path_changed.emit(self.current_path)

        # 4. Start Background Task
        worker = Worker(self.mod_service.get_item_skeletons, path, self.context)
        worker.signals.result.connect(
            lambda result: self._on_skeletons_loaded(result, token_for_this_load)
        )
        worker.signals.error.connect(self._on_skeletons_error)

        thread_pool = QThreadPool.globalInstance()
        if thread_pool:
            thread_pool.start(worker)

    def unload_items(self):
        """Clears all items from the view and state to save memory and reset the view."""
        logger.info(f"Unloading all items for context: '{self.context}'")
        self.master_list = []
        self.displayed_items = []
        self.current_path = None
        self.current_load_token += 1  # Invalidate any ongoing loads

        # Emit signal with empty list to clear the UI
        self.items_updated.emit([], None)

        # Reset navigation root
        self.navigation_root = None

        # If this is foldergrid, also clear the breadcrumb
        if self.context == "foldergrid":
            self.path_changed.emit(Path())

    def request_item_hydration(self, item_id: str):
        """Flow 2.2 & 2.3: Lazy-loads full details for a visible item."""
        if item_id in self._hydrating_ids:
            return  # Already being processed

        item = next((i for i in self.master_list if i.id == item_id), None)

        # Guard clauses: don't hydrate if not found, not a skeleton, or no game context

        if not item or not item.is_skeleton or not self.current_game:
            return

        self._hydrating_ids.add(item_id)

        worker = Worker(
            self.mod_service.hydrate_item, item, self.current_game.name, self.context
        )
        worker.signals.result.connect(self._on_item_hydrated)
        worker.signals.error.connect(
            lambda err, id=item_id: self._on_hydration_error(err, id)
        )

        thread_pool = QThreadPool.globalInstance()
        if thread_pool:
            thread_pool.start(worker)
        else:
            logger.critical(
                f"Could not get QThreadPool instance for hydrating item {item_id}."
            )
            self._on_hydration_error((None, "Thread pool unavailable", ""), item_id)

    def update_item_in_list(self, updated_item):
        """Flow 5.1: Updates a single item in the master list and refreshes the view."""
        if not updated_item:
            return

        logger.info(
            f"Receiving external update for item '{updated_item.actual_name}' in context '{self.context}'"
        )
        try:
            # Change items on Master List
            master_idx = next(
                i
                for i, item in enumerate(self.master_list)
                if item.id == updated_item.id
            )
            self.master_list[master_idx] = updated_item

            # Change also on the displayed list
            display_idx = next(
                i
                for i, item in enumerate(self.displayed_items)
                if item.id == updated_item.id
            )
            self.displayed_items[display_idx] = updated_item

            # Ask UI to update a specific widget
            self.item_needs_update.emit(self._create_dict_from_item(updated_item))
        except StopIteration:
            logger.warning(
                f"Item {updated_item.id} to update was not found in the list."
            )

    # ---Filtering and Searching ---

    def _on_skeletons_loaded(self, result: dict, received_token: int):
        """Handles the result from the skeleton loading worker."""
        # Race Condition Check: If this result is from an old request, ignore it.
        if received_token != self.current_load_token:
            logger.warning(
                f"Ignoring stale skeleton load result with token {received_token}"
            )
            return

        self.loading_finished.emit()  # Hide shimmer

        if not result["success"]:
            self.toast_requested.emit(f"Error: {result['error']}", "error")
            self.items_updated.emit([])  # Ensure view is empty
            self.load_completed.emit(False)
            return

        logger.info(f"Successfully loaded {len(result['items'])} skeletons.")
        self.master_list = result["items"]

        # --- Selection logic ---
        item_id_to_select = None

        # check if there is a newly created item to select
        if self._item_to_select_after_load:
            item = next((i for i in self.master_list if i.actual_name == self._item_to_select_after_load), None)
            if item:
                logger.info(f"Identified newly created item to select: '{item.actual_name}'")
                item_id_to_select = item.id
            self._item_to_select_after_load = None # Reset state

        # if no new item to select, check if there is a previously selected item to restore
        elif self.last_selected_item_id:
            item = next((i for i in self.master_list if i.id == self.last_selected_item_id), None)
            if not item and self.last_selected_item_name:
                item = next(
                    (
                        i
                        for i in self.master_list
                        if i.actual_name == self.last_selected_item_name
                    ),
                    None,
                )
            if item:
                logger.info(f"Identified previously selected item to restore: '{item.actual_name}'")
                item_id_to_select = item.id
                self.last_selected_item_id = item.id
                self.last_selected_item_name = item.actual_name
            else:
                logger.warning(
                    f"Previously selected item '{self.last_selected_item_id}' not found after refresh. Invalidating selection."
                )
                self.last_selected_item_id = None
                self.last_selected_item_name = None
                self.active_selection_changed.emit(None)
                self.selection_invalidated.emit()
        # -----------------------------------------------------------------

        # --- Default foldergrid selection (first enabled, or first if none enabled) ---
        if item_id_to_select is None and self.context == CONTEXT_FOLDERGRID and self.master_list:
            first_enabled = next(
                (item for item in self.master_list if item.status == ModStatus.ENABLED),
                None,
            )
            if first_enabled:
                item_id_to_select = first_enabled.id
                self.last_selected_item_id = first_enabled.id
                self.last_selected_item_name = first_enabled.actual_name
                logger.info(f"Auto-selecting first enabled mod: '{first_enabled.actual_name}'")
            elif self.master_list:
                first_item = self.master_list[0]
                item_id_to_select = first_item.id
                self.last_selected_item_id = first_item.id
                self.last_selected_item_name = first_item.actual_name
                logger.info(f"No enabled mods. Auto-selecting first mod: '{first_item.actual_name}'")
        # -----------------------------------------------------------------

        self._update_available_filters()
        self.apply_filters_and_search(item_id_to_select=item_id_to_select)
        self.load_completed.emit(True)

        # --- FIX: Add logic to restore selection after loading is complete ---
        if self.last_selected_item_id:
            # Check if the previously selected item still exists in the new list
            found_item = next(
                (
                    item
                    for item in self.master_list
                    if item.id == self.last_selected_item_id
                ),
                None,
            )
            if not found_item and self.last_selected_item_name:
                found_item = next(
                    (
                        item
                        for item in self.master_list
                        if item.actual_name == self.last_selected_item_name
                    ),
                    None,
                )

            if found_item:
                self.last_selected_item_id = found_item.id
                self.last_selected_item_name = found_item.actual_name
                # If it exists, re-emit the signal to apply the selection style in the UI.
                logger.info(
                    f"Restoring selection for item ID: {self.last_selected_item_id}"
                )
                self.active_selection_changed.emit(self.last_selected_item_id)
            else:
                # --- FIX: The previously selected item no longer exists ---
                logger.warning(
                    f"Previously selected item '{self.last_selected_item_id}' not found after refresh. Invalidating selection."
                )
                # 1. Reset the state
                self.last_selected_item_id = None
                self.last_selected_item_name = None

                # 2. Emit the new, specific signal for this event
                self.active_selection_changed.emit(None)
                self.selection_invalidated.emit()

    def _on_skeletons_error(self, error_info: tuple):
        """Handles unexpected errors from the worker thread."""
        self.loading_finished.emit()  # Hide shimmer

        exctype, value, tb = error_info
        logger.critical(f"Failed to load skeletons: {value}\n{tb}")
        self.toast_requested.emit(
            "A critical error occurred while loading mods.", "error"
        )

    def _on_item_hydrated(self, hydrated_item: BaseModItem):
        """
        Updates the master list with the hydrated item and notifies the view.
        This method now correctly differentiates between ObjectItem and FolderItem.
        """
        self._hydrating_ids.discard(hydrated_item.id)

        # ---SECTION: Differentiate item type ---

        # 1. Create a base dictionary with common attributes

        base_data = {
            "id": hydrated_item.id,
            "actual_name": hydrated_item.actual_name,
            "is_enabled": hydrated_item.status,
            "is_pinned": hydrated_item.is_pinned,
            "is_skeleton": hydrated_item.is_skeleton,
        }

        hydrated_data = {}

        # 2. Check the instance type and add specific attributes

        if isinstance(hydrated_item, ObjectItem):
            if isinstance(hydrated_item, CharacterObjectItem):
                # It's an item for the objectlist

                object_item_data = {
                    "thumbnail_path": hydrated_item.thumbnail_path,
                    "object_type": hydrated_item.object_type,
                    "tags": hydrated_item.tags,
                    "gender": hydrated_item.gender,
                    "rarity": hydrated_item.rarity,
                    "element": hydrated_item.element,
                }
                hydrated_data = {**base_data, **object_item_data}
            elif isinstance(hydrated_item, GenericObjectItem):
                # It's a generic object item

                generic_item_data = {
                    "thumbnail_path": hydrated_item.thumbnail_path,
                    "object_type": hydrated_item.object_type,
                    "tags": hydrated_item.tags,
                }
                hydrated_data = {**base_data, **generic_item_data}
        elif isinstance(hydrated_item, FolderItem):
            # It's an item for the foldergrid

            folder_item_data = {
                "author": hydrated_item.author,
                "description": hydrated_item.description,
                "tags": hydrated_item.tags,
                "preview_images": hydrated_item.preview_images,
                "is_navigable": hydrated_item.is_navigable,
                "is_safe": hydrated_item.is_safe,
            }
            hydrated_data = {**base_data, **folder_item_data}

        else:
            logger.error(
                f"Received an unknown item type during hydration: {type(hydrated_item)}"
            )
            return
        # ---END REVISED SECTION ---

        try:
            # The rest of the logic for the list and signal issuers remain the same

            master_idx = self.master_list.index(
                next(i for i in self.master_list if i.id == hydrated_item.id)
            )
            self.master_list[master_idx] = hydrated_item

            display_idx = self.displayed_items.index(
                next(i for i in self.displayed_items if i.id == hydrated_item.id)
            )
            self.displayed_items[display_idx] = hydrated_item

            hydrated_data = self._create_dict_from_item(hydrated_item)
            self.item_needs_update.emit(hydrated_data)

            # If the hydrated item is the currently selected foldergrid item,
            # refresh the preview panel so it shows the full data (preview_images, etc.)
            if self.context == CONTEXT_FOLDERGRID and self.last_selected_item_id == hydrated_item.id:
                self.foldergrid_item_modified.emit(hydrated_item)
        except (ValueError, StopIteration):
            logger.warning(
                f"Could not find item {hydrated_item.id} to update post-hydration. List may have been reloaded."
            )
        except Exception as e:
            logger.error(
                f"Unhandled error while hydrating item {hydrated_item.id}: {e}",
                exc_info=True,
            )

    def _on_hydration_error(self, error_info: tuple, item_id: str):
        """Handles errors during hydration and cleans up."""
        self._hydrating_ids.discard(item_id)
        exctype, value, tb = error_info
        logger.error(f"Failed to hydrate item {item_id}: {value}\n{tb}")
