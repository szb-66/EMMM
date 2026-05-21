# App/viewmodels/mod list vm.py


import dataclasses
from pathlib import Path
from typing import List
from PyQt6.QtCore import QObject, pyqtSignal, QThreadPool
from PyQt6.QtGui import QPixmap
from app.models.game_model import Game
from app.models.mod_item_model import (
    ModStatus,
    ModType,
    BaseModItem,
    ObjectItem,
    CharacterObjectItem,
    GenericObjectItem,
    FolderItem,
)
from app.utils.logger_utils import logger
from app.utils.async_utils import Worker
from app.services.thumbnail_service import ThumbnailService
from app.services.database_service import DatabaseService
from app.services.mod_service import ModService
from app.services.workflow_service import WorkflowService
from app.utils.system_utils import SystemUtils
from app.utils.async_utils import debounce
from app.core.constants import DEBOUNCE_DELAY_MS, CONTEXT_OBJECTLIST, CONTEXT_FOLDERGRID

class ModListViewModel(QObject):
    """
    Manages state and logic for both the objectlist and foldergrid panels,
    adapting its behavior based on the provided context.
    """

    # ---Signals for UI State & Feedback ---
    creation_tasks_prepared = pyqtSignal(list)
    loading_started = pyqtSignal()
    loading_finished = pyqtSignal()
    items_updated = pyqtSignal(list,object)
    item_needs_update = pyqtSignal(object)
    item_processing_started = pyqtSignal(str)
    item_processing_finished = pyqtSignal(str, bool)
    toast_requested = pyqtSignal(
        str, str
    )  # message, level ('info', 'error', 'success')
    active_selection_changed = pyqtSignal(object)
    selection_invalidated = pyqtSignal()
    empty_state_changed = pyqtSignal(str, str)
    filter_state_changed = pyqtSignal(bool, int)
    clear_search_text = pyqtSignal()
    manual_sync_required = pyqtSignal(str, list)
    reconciliation_progress_updated = pyqtSignal(int, int)  # current, total
    # ---Signals for Panel-Specific UI ---
    path_changed = pyqtSignal(Path)
    selection_changed = pyqtSignal(bool)
    available_filters_changed = pyqtSignal(dict)
    password_requested = pyqtSignal(dict)
    failure_report_requested = pyqtSignal(list)

    # ---Signals for Bulk Operations ---
    bulk_operation_started = pyqtSignal()
    bulk_operation_finished = pyqtSignal(list)  # list of failed items

    # ---Signals for Cross-ViewModel Communication ("Efek Domino") ---
    active_object_modified = pyqtSignal(object)
    active_object_deleted = pyqtSignal(str)
    foldergrid_item_modified = pyqtSignal(object)
    watched_refresh_suppression_requested = pyqtSignal(str)
    load_completed = pyqtSignal(bool)
    sync_confirmation_requested = pyqtSignal(list)
    game_type_setup_required = pyqtSignal(str)
    object_created = pyqtSignal(dict)
    list_refresh_requested = pyqtSignal()
    exclusive_activation_confirmation_requested = pyqtSignal(dict)

    def __init__(
        self,
        context: str,
        mod_service: ModService,
        workflow_service: WorkflowService,
        database_service: DatabaseService,
        thumbnail_service: ThumbnailService,
        system_utils: SystemUtils,
    ):
        super().__init__()
        # ---Injected Services ---
        self.context = context  # 'objectlist' or 'foldergrid'
        self.mod_service = mod_service
        self.workflow_service = workflow_service
        self.database_service = database_service
        self.thumbnail_service = thumbnail_service
        self.system_utils = system_utils

        # ---Internal State ---
        self.master_list = []
        self.displayed_items = []
        self.selected_item_ids = set()
        self.active_filters = {}
        self.search_query = ""
        self.current_path = None
        self.current_load_token = 0
        self._hydrating_ids = set()
        self.current_game: Game | None = None
        self.navigation_root: Path | None = None
        self._processing_ids = set()
        self.last_selected_item_id: str | None = None
        self.last_selected_item_name: str | None = None
        self.active_category_filter: ModType = ModType.CHARACTER
        self._item_to_select_after_load: str | None = None
        self._active_workers = []
        self.thumbnail_service.thumbnail_generated.connect(self._on_thumbnail_generated)

    # ---Loading and Data Management ---

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

    def set_filters(self, filters: dict):
        """
        Flow 5.1: Sets the active detail filters (e.g., rarity, element)
        and triggers a view update.
        """
        logger.info(f"Applying detailed filters: {filters}")
        self.active_filters = filters
        self.apply_filters_and_search()

    def clear_filters(self):
        """
        Clears all active detail filters and triggers a view update.
        """
        if not self.active_filters:
            return

        logger.info("Clearing all detailed filters.")
        self.active_filters = {}
        self.apply_filters_and_search()

    @debounce(DEBOUNCE_DELAY_MS)
    def on_search_query_changed(self, query: str):
        """
        Flow 5.1: Handles live text changes from the search bar with a debounce delay.
        """
        # Sanitize the input query
        sanitized_query = query.lower().strip()

        # Only trigger a refresh if the query has actually changed
        if self.search_query == sanitized_query:
            return

        logger.info(f"Search query changed to: '{sanitized_query}'")
        self.search_query = sanitized_query
        self.apply_filters_and_search()


    # ---Single Item Actions ---

    def toggle_item_status(self, item_id: str):
        """
        Flow 3.1a: Initiates the background task to toggle an item's status.
        """
        if item_id in self._processing_ids:
            logger.warning(
                f"Item '{item_id}' is already being processed. Ignoring request."
            )
            return

        item_to_toggle = next(
            (item for item in self.master_list if item.id == item_id), None
        )

        if not item_to_toggle:
            logger.error(
                f"toggle_item_status: Item with ID '{item_id}' not found in master list."
            )
            return

        logger.info(f"Toggling status for item: {item_to_toggle.actual_name}")

        # 1. Mark the item as being processed & tell UI

        self._processing_ids.add(item_id)
        self.watched_refresh_suppression_requested.emit(self.context)
        self.item_processing_started.emit(item_id)

        # 2. Create and run a worker in the background thread

        worker = Worker(self.mod_service.toggle_status, item_to_toggle)
        worker.signals.result.connect(
            lambda result, id=item_id: self._on_toggle_status_finished(id, result)
        )
        worker.signals.error.connect(
            lambda error, id=item_id: self._on_toggle_status_error(id, error)
        )

        thread_pool = QThreadPool.globalInstance()
        if thread_pool:
            thread_pool.start(worker)
        else:
            logger.critical(
                f"Could not get QThreadPool instance for toggling item {item_id}."
            )
            self._on_toggle_status_error(item_id, (None, "Thread pool unavailable", ""))

    def toggle_pin_status(self, item_id: str):
        """
        [IMPLEMENTED] Initiates the background process for pinning or unpinning an item.
        """
        if item_id in self._processing_ids:
            return

        item_to_pin = next((item for item in self.master_list if item.id == item_id), None)
        if not item_to_pin:
            logger.error(f"Cannot toggle pin: Item with ID '{item_id}' not found.")
            return

        logger.info(f"Request to toggle pin for '{item_to_pin.actual_name}'.")
        self._processing_ids.add(item_id)
        self.watched_refresh_suppression_requested.emit(self.context)
        self.item_processing_started.emit(item_id)

        worker = Worker(self.mod_service.toggle_pin_status, item_to_pin)
        worker.signals.result.connect(self._on_pin_status_finished)
        worker.signals.error.connect(
            lambda err, id=item_id: self._on_generic_worker_error(id, err, "pin toggle")
        )

        QThreadPool.globalInstance().start(worker)


    # --- Ganti slot _on_pin_status_finished yang sebelumnya kosong ---
    def _on_pin_status_finished(self, result: dict):
        """
        [IMPLEMENTED] Handles the result of the pin/unpin operation.
        Updates the item in the model and triggers a re-sort of the UI.
        """
        item_id = result.get("item_id")
        if not item_id: return

        self._processing_ids.discard(item_id)
        self.item_processing_finished.emit(item_id, result.get("success", False))

        if result.get("success"):
            new_item = result.get("data")

            # Update the item in the master list
            self.update_item_in_list(new_item)

            # Re-apply filters AND sorting. The sorting logic will automatically
            # move the pinned item to the top.
            self.apply_filters_and_search()

            self.toast_requested.emit("Pin status updated.", "success")
        else:
            self.toast_requested.emit(f"Failed to update pin status: {result.get('error')}", "error")


    def rename_item(self, item_id: str, new_name: str):
        """
        Flow 6.3: Initiates the background process for renaming an item.
        """
        if item_id in self._processing_ids:
            return

        item_to_rename = next((item for item in self.master_list if item.id == item_id), None)
        if not item_to_rename:
            logger.error(f"Cannot rename: Item with ID '{item_id}' not found.")
            return

        logger.info(f"Request to rename '{item_to_rename.actual_name}' to '{new_name}'.")
        self._processing_ids.add(item_id)
        self.watched_refresh_suppression_requested.emit(self.context)
        self.item_processing_started.emit(item_id)

        worker = Worker(self.mod_service.rename_item, item_to_rename, new_name)
        worker.signals.result.connect(self._on_rename_finished)
        worker.signals.error.connect(
            lambda error_info, id=item_id: self._on_rename_error(id, error_info)
        )
        QThreadPool.globalInstance().start(worker)


    def _on_rename_finished(self, result: dict):
        """
        [REVISED] Handles the result of the rename operation.
        The item_id is now retrieved from the result dictionary.
        """
        # The service should also return the item_id for context
        item_id = result.get("item_id")
        if not item_id:
            logger.error("Rename finished but result dictionary is missing 'item_id'.")
            # Fallback: attempt to stop all processing animations
            self.item_processing_finished.emit("", False)
            return

        self._processing_ids.discard(item_id)
        self.item_processing_finished.emit(item_id, result.get("success", False))

        if not result.get("success"):
            self.toast_requested.emit(result.get("error", "An unknown error occurred."), "error")
            return

        new_item = result.get("data")
        self.update_item_in_list(new_item)
        self.toast_requested.emit(f"Renamed to '{new_item.actual_name}' successfully.", "success")

        if self.context == CONTEXT_OBJECTLIST and self.last_selected_item_id == item_id:
            self.active_object_modified.emit(new_item)

    def _on_rename_error(self, item_id: str, error_info: tuple):
        """
        Handles critical failures from the rename worker thread.
        """
        self._processing_ids.discard(item_id)
        # Ensure the UI is unblocked
        self.item_processing_finished.emit(item_id, False)

        exctype, value, tb = error_info
        logger.critical(f"A worker error occurred while renaming item {item_id}: {value}\n{tb}")
        self.toast_requested.emit("A critical error occurred during rename. Please check the logs.", "error")

    def delete_item(self, item_id: str):
        """
        [IMPLEMENTED] Initiates the background process for moving an item
        to the recycle bin.
        """
        if item_id in self._processing_ids:
            return

        item_to_delete = next((item for item in self.master_list if item.id == item_id), None)
        if not item_to_delete:
            logger.error(f"Cannot delete: Item with ID '{item_id}' not found.")
            return

        logger.info(f"Request to delete '{item_to_delete.actual_name}'. Starting worker.")
        self._processing_ids.add(item_id)
        self.watched_refresh_suppression_requested.emit(self.context)
        self.item_processing_started.emit(item_id)

        worker = Worker(self.mod_service.delete_item, item_to_delete)
        worker.signals.result.connect(self._on_delete_finished)
        worker.signals.error.connect(
            lambda error_info, id=item_id: self._on_delete_error(id, error_info)
        )

        QThreadPool.globalInstance().start(worker)

    def _on_delete_error(self, item_id: str, error_info: tuple):
        """
        [NEW] Handles critical failures from the delete worker thread.
        """
        self._processing_ids.discard(item_id)
        # Ensure the UI is unblocked
        self.item_processing_finished.emit(item_id, False)

        exctype, value, tb = error_info
        logger.critical(f"A worker error occurred while deleting item {item_id}: {value}\n{tb}")
        self.toast_requested.emit("A critical error occurred during deletion. Please check the logs.", "error")

    def open_in_explorer(self, item_id: str):
        """
        Flow 4.3: Finds the item by its ID and requests SystemUtils
        to open its folder path in the system's file explorer.
        """
        logger.info(f"Request received to open item '{item_id}' in explorer.")

        # 1. Find the item model in the master list using its ID.
        item = next((i for i in self.master_list if i.id == item_id), None)

        if not item:
            logger.error(
                f"Cannot open in explorer: Item with id '{item_id}' not found."
            )
            self.toast_requested.emit("Could not find the selected item.", "error")
            return

        # 2. Get the folder path from the item model.
        path_to_open = item.folder_path

        # 3. Delegate the action to the utility class.
        self.system_utils.open_path_in_explorer(path_to_open)

    # ---Selection Management ---

    def set_item_selected(self, item_id: str, is_selected: bool):
        """Flow 3.2: Updates the set of selected item IDs."""
        pass

    # ---Bulk & Creation Actions ---

    def initiate_bulk_action(self, action_type: str, **kwargs):
        """Flow 3.2: Central method to start any bulk action (enable, disable, tag)."""
        pass

    def initiate_create_mods(self, tasks: list):
        """Flow 4.1.A: Starts the creation workflow for new mods in foldergrid."""
        pass

    def get_all_item_names(self) -> list[str]:
        """Returns a list of all actual_names in the master list for duplicate checking."""
        return [item.actual_name for item in self.master_list]

    def initiate_create_objects(self, tasks: list):
        """
        Flow 4.1.B Step 4: Starts the background workflow for creating new objects.
        """
        if not tasks:
            return

        if not self.current_game or not self.current_game.path.is_dir():
            self.toast_requested.emit("Cannot create object: Active game path is not set.", "error")
            return

        parent_path = self.current_game.path
        logger.info(f"Initiating creation for {len(tasks)} object(s) in '{parent_path}'.")

        self.bulk_operation_started.emit()

        worker = Worker(
            self.workflow_service.execute_object_creation,
            tasks,
            parent_path
        )
        worker.signals.result.connect(
            lambda result, tasks_info=tasks: self._on_creation_finished(result, tasks_info)
        )
        worker.signals.error.connect(self._on_creation_error)
        worker.signals.progress.connect(self._on_creation_progress_updated)

        QThreadPool.globalInstance().start(worker)

    def get_reconciliation_preview(self) -> dict:
        """
        [NEW] Performs a "dry run" of the reconciliation logic to get the counts
        of items that will be created and updated.
        """
        if not self.current_game or not self.current_game.game_type:
            return {"to_create": 0, "to_update": 0}

        logger.info("Starting reconciliation preview for current game.")
        game_type = self.current_game.game_type
        all_local_items = self.master_list
        all_db_objects = self.database_service.get_all_objects_for_game(game_type)

        if not all_db_objects:
            return {"to_create": 0, "to_update": 0}

        # --- Logic to find matches and count updates ---
        matched_db_names = set()
        count_to_update = 0
        for local_item in all_local_items:
            match_info = self.database_service.find_best_object_match(all_db_objects, local_item.actual_name)
            if match_info and match_info.get("score", 0) > 0.8:
                best_match = match_info["match"]
                count_to_update += 1
                matched_db_names.add(best_match.get("name", "").lower())

        # --- Logic to count creations ---
        count_to_create = 0
        for db_obj in all_db_objects:
            if db_obj.get("name", "").lower() not in matched_db_names:
                count_to_create += 1

        return {"to_create": count_to_create, "to_update": count_to_update}

    def initiate_randomize(self):
        """Flow 6.2.B: Starts the randomization workflow for the current group."""
        pass

    def _create_dict_from_item(self, item: BaseModItem) -> dict:
        """A helper function to convert any BaseModItem object to a dict for the view."""
        # 1. Start with attributes common to all items

        data = {
            "id": item.id,
            "actual_name": item.actual_name,
            "is_enabled": (item.status == ModStatus.ENABLED),
            "is_pinned": item.is_pinned,
            "is_skeleton": item.is_skeleton,
            "folder_path": item.folder_path,
        }
        # 2. Add attributes specific to the item type

        if isinstance(item, ObjectItem):
            if isinstance(item, CharacterObjectItem):
                data.update(
                    {
                        "thumbnail_path": item.thumbnail_path,
                        "object_type": item.object_type,
                        "tags": item.tags,
                        "gender": item.gender,
                        "rarity": item.rarity,
                        "element": item.element,
                    }
                )
            elif isinstance(item, GenericObjectItem):
                data.update(
                    {
                        "thumbnail_path": item.thumbnail_path,
                        "object_type": item.object_type,
                        "tags": item.tags,
                    }
                )
        elif isinstance(item, FolderItem):
            data.update(
                {
                    "author": item.author,
                    "description": item.description,
                    "tags": item.tags,
                    "preview_images": item.preview_images,
                    "is_navigable": item.is_navigable,
                    "is_safe": item.is_safe,
                }
            )
        return data

    # ---Private/Internal Logic ---

    def apply_filters_and_search(self, item_id_to_select: str = None):
        """
        Filters and sorts the master list based on all active criteria,
        then emits the result for the view to render.
        """
        source_list = self.master_list

        # STAGE 1: Apply main category filter (Character vs Other) if in objectlist context
        if self.context == CONTEXT_OBJECTLIST:
            if self.active_category_filter == ModType.CHARACTER:
                filtered_items = [item for item in source_list if isinstance(item, CharacterObjectItem)]
            else:
                filtered_items = [item for item in source_list if isinstance(item, GenericObjectItem)]
        else:
            filtered_items = source_list

        # STAGE 2: Apply detailed filters from self.active_filters
        if self.active_filters:
                items_after_detail_filter = []
                for item in filtered_items:
                    match = True
                    for key, value in self.active_filters.items():
                        item_value = getattr(item, key, None)

                        # Add logging to see the comparison
                        logger.debug(f"Filtering '{item.actual_name}': Attr '{key}' (Value: {item_value}) vs Filter (Value: {value})")

                        if key == 'tags' and isinstance(value, list):
                            # Handle multi-select for tags
                            if not isinstance(item_value, list) or not set(value).issubset(set(item_value)):
                                match = False
                                break
                        else:
                            # Handle single-select for other fields
                            if item_value != value:
                                match = False
                                break
                    if match:
                        items_after_detail_filter.append(item)
                filtered_items = items_after_detail_filter


        # STAGE 3: Sort the final list
        scored_results = []
        if not self.search_query:
            # If search is empty, assign a neutral score to all items
            scored_results = [(item, 99) for item in filtered_items]
        else:
            # If search is active, score each item based on relevance
            for item in filtered_items:
                score = 99  # Default non-match score

                # Context-aware scoring
                if self.context == CONTEXT_OBJECTLIST:
                    if self.search_query in item.actual_name.lower():
                        score = 1
                    elif item.tags and any(self.search_query in tag.lower() for tag in item.tags):
                        score = 2
                    elif isinstance(item, CharacterObjectItem):
                        if (item.element and self.search_query in item.element.lower()) or \
                            (item.weapon and self.search_query in item.weapon.lower()):
                            score = 3

                elif self.context == CONTEXT_FOLDERGRID:
                    if self.search_query in item.actual_name.lower():
                        score = 1
                    elif item.tags and any(self.search_query in tag.lower() for tag in item.tags):
                        score = 2
                    elif item.author and self.search_query in item.author.lower():
                        score = 3
                    elif item.description and self.search_query in item.description.lower():
                        score = 4

                # Only include items that have a match (score < 99)
                if score < 99:
                    scored_results.append((item, score))

        # --- STAGE 4: Sort the final list ---
        # Sort by: 1. Score (relevance), 2. Pinned, 3. Enabled, 4. Name
        sorted_results = sorted(
            scored_results,
            key=lambda x: (x[1], not x[0].is_pinned, x[0].status != ModStatus.ENABLED, x[0].actual_name.lower())
        )

        # Extract only the item objects from the (item, score) tuples
        self.displayed_items = [item for item, score in sorted_results]

        # --- STAGE 5: Check for empty results and emit CONTEXT-AWARE state ---
        if not self.displayed_items:
            # This block is now context-aware
            if not self.master_list:
                # Case 1: The folder itself is truly empty.
                if self.context == CONTEXT_OBJECTLIST:
                    title = "No Objects Found"
                    subtitle = "This game's mods folder seems to be empty.\nCreate a new object to get started."
                else: # CONTEXT_FOLDERGRID
                    title = "Folder is Empty"
                    subtitle = "Drag and drop a .zip file or folder here to add a new mod."
                self.empty_state_changed.emit(title, subtitle)

            elif self.search_query or self.active_filters:
                # Case 2: A search/filter was applied and yielded no results (generic message).
                title = "No Matching Results"
                subtitle = "Try adjusting your filter or search terms."
                self.empty_state_changed.emit(title, subtitle)

            else:
                # Case 3: No search/filter, but the base list for the context is empty.
                # This only really applies to the objectlist's category filter.
                if self.context == CONTEXT_OBJECTLIST:
                    category_name = self.active_category_filter.value
                    title = f"No {category_name}s Found"
                    subtitle = f"This category is empty. You can add mods to it."
                    self.empty_state_changed.emit(title, subtitle)
                else:
                    # This case is unlikely for foldergrid but provides a fallback.
                    title = "Folder is Empty"
                    subtitle = "This folder contains no mods."
                    self.empty_state_changed.emit(title, subtitle)

        # --- STAGE 6: Emit filter state for the result bar (BARU) ---
        is_filter_active = bool(self.active_filters or self.search_query)
        found_count = len(self.displayed_items)

        # Show bar only if a filter/search is active AND there are results
        show_bar = is_filter_active and found_count > 0
        self.filter_state_changed.emit(show_bar, found_count)

        # --- STAGE 7: Prepare and emit data for the view ---
        view_data = [self._create_dict_from_item(item) for item in self.displayed_items]
        self.items_updated.emit(view_data, item_id_to_select)

    # ---Private Slots for Async Results ---
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

    def set_active_selection(self, item_id: str | None):
        """
        Called by the View when an item is single-clicked.
        This method updates the state and notifies the view.
        """
        if self.last_selected_item_id != item_id:
            self.last_selected_item_id = item_id
            selected_item = next((i for i in self.master_list if i.id == item_id), None)
            self.last_selected_item_name = (
                selected_item.actual_name if selected_item else None
            )
            logger.debug(
                f"Active selection changed in context '{self.context}': {item_id}"
            )
            self.active_selection_changed.emit(item_id)

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
        except (ValueError, StopIteration):
            logger.warning(
                f"Could not find item {hydrated_item.id} to update post-hydration. List may have been reloaded."
            )

    def _on_hydration_error(self, error_info: tuple, item_id: str):
        """Handles errors during hydration and cleans up."""
        self._hydrating_ids.discard(item_id)
        exctype, value, tb = error_info
        logger.error(f"Failed to hydrate item {item_id}: {value}\n{tb}")

    def _on_toggle_status_finished(self, item_id: str, result: dict):
        """
        Handles the result of a single item status toggle operation.
        This version correctly handles the full model object returned by the service.
        """
        self._processing_ids.discard(item_id)

        if not result.get("success"):
            self.toast_requested.emit(result.get("error", "Unknown error"), "error")
            self.item_processing_finished.emit(item_id, False)
            return

        try:
            # 1. The 'data' from the service is now the complete, updated model object.
            #    No need to build it here.
            new_item = result.get("data")
            if not new_item:
                raise ValueError("Service succeeded but returned no data object.")

            # 2. Find the index of the old item to replace it.
            master_idx = next(
                i for i, item in enumerate(self.master_list) if item.id == item_id
            )

            # 3. Replace the old item with the new one in both internal lists.
            self.master_list[master_idx] = new_item

            try:
                display_idx = next(
                    i
                    for i, item in enumerate(self.displayed_items)
                    if item.id == item_id
                )
                self.displayed_items[display_idx] = new_item
            except StopIteration:
                # Item was not in the displayed list (due to filters), which is fine.
                pass

            logger.info(f"Successfully toggled status for item: {new_item.actual_name}")

            # 4. Emit signals to UI for updates (the rest of the logic is the same).
            self.item_needs_update.emit(self._create_dict_from_item(new_item))
            self.item_processing_finished.emit(item_id, True)

            # Emit context-specific signals for domino effects.
            if self.context == CONTEXT_OBJECTLIST:
                self.active_object_modified.emit(new_item)
            elif self.context == CONTEXT_FOLDERGRID:
                self.foldergrid_item_modified.emit(new_item)

        except (StopIteration, KeyError, ValueError) as e:
            logger.error(f"Error updating item state after toggle: {e}", exc_info=True)
            self.item_processing_finished.emit(item_id, False)

    def _on_toggle_status_error(self, item_id: str, error_info: tuple):
        """Handles unexpected worker errors during toggle."""
        self._processing_ids.discard(item_id)
        self.item_processing_finished.emit(item_id, False)  # Make sure UI is unblock

        exctype, value, tb = error_info
        logger.critical(
            f"A worker error occurred while toggling item {item_id}: {value}\n{tb}"
        )
        self.toast_requested.emit(
            "A critical error occurred. Please check the logs.", "error"
        )

    def _on_delete_finished(self, result: dict):
        """
        [IMPLEMENTED] Handles the result of the delete operation.
        Removes the item from the internal lists and refreshes the UI.
        """
        item_id = result.get("item_id")
        if not item_id:
            return

        self._processing_ids.discard(item_id)
        # signal to UI that processing is finished
        self.item_processing_finished.emit(item_id, result.get("success", False))

        if result.get("success"):
            item_name = result.get("item_name", "Item")
            self.toast_requested.emit(f"'{item_name}' moved to Recycle Bin.", "success")

            # Delete the item from both master and displayed lists
            self.master_list = [item for item in self.master_list if item.id != item_id]
            self.displayed_items = [item for item in self.displayed_items if item.id != item_id]

            # Call apply_filters_and_search to refresh the UI correctly
            self.apply_filters_and_search()

            # --- Domino Effect Logic (if the active item is deleted) ---
            if self.context == CONTEXT_FOLDERGRID and self.last_selected_item_id == item_id:
                self.selection_invalidated.emit() # Notify PreviewPanel to clear itself

            elif self.context == CONTEXT_OBJECTLIST and self.last_selected_item_id == item_id:
                self.active_object_deleted.emit(item_id) # Notify MainWindowViewModel to clear foldergrid

        else:
            self.toast_requested.emit(f"Failed to delete item: {result.get('error')}", "error")


    def _on_bulk_action_finished(self, result: dict):
        """Handles the result of a bulk action like enable, disable, or tag (Flow 3.2)."""
        pass

    def _on_creation_finished(self, result: dict, tasks_info: list):
        """
        [REVISED] Handles the creation result with intelligent logic for both
        single (manual) and bulk (sync) creation scenarios.
        """
        self.bulk_operation_finished.emit([])

        successful_items = result.get("successful_items", [])
        failed_items = result.get("failed_items", [])
        cancelled_count = result.get("cancelled_count", 0)

        # --- STAGE 1: Check for Password-Protected Files ---
        # This is the highest priority action after a workflow finishes.
        password_tasks = []
        other_failures = []

        for failure in failed_items:
            # Check if the reason for failure was a password request
            if failure.get("reason") == "Archive is password-protected.":
                password_tasks.append(failure['task'])
            else:
                other_failures.append(failure)

        # If any tasks require a password, emit a signal for the first one
        if password_tasks:
            self.password_requested.emit(password_tasks[0])
            # We stop here and wait for the user to provide a password
            return

        # --- STAGE 2: Final Reporting & UI Unlocking ---
        self.bulk_operation_finished.emit(other_failures)

        # --- STAGE 3: Smart UX Logic for Toasts ---
        successful_count = len(successful_items)
        failed_count = len(other_failures)
        cancelled_count = result.get("cancelled_count", 0)

        # Handle the special case for a single, perfect manual creation
        if successful_count == 1 and failed_count == 0 and cancelled_count == 0 and tasks_info[0].get("type") == "manual":
            created_object_data = tasks_info[0].get("data", {})
            object_name = created_object_data.get("name", "New Mod")
            self.toast_requested.emit(f"Successfully created '{object_name}'.", "success")
            if self.context == CONTEXT_OBJECTLIST:
                self._item_to_select_after_load = object_name
                self.object_created.emit(created_object_data)
        else:
            # 1. Build the summary message
            summary_parts = []
            if successful_count > 0:
                summary_parts.append(f"{successful_count} created")
            if failed_count > 0:
                summary_parts.append(f"{failed_count} failed")
            if cancelled_count > 0:
                summary_parts.append(f"{cancelled_count} cancelled")

            logger.info(f"Creation Summary: {', '.join(summary_parts)}")
            summary_content = "Process finished: " + ", ".join(summary_parts) + "."
            level = "success" if failed_count == 0 and cancelled_count == 0 else "warning"

            # 2. ALWAYS show the summary toast
            self.toast_requested.emit(summary_content, level)

            # 3. If there were failures, ALSO request the details dialog
            if failed_count > 0:
                self.failure_report_requested.emit(other_failures)


        # --- STAGE 4: Smart UI Refresh ---
        # Only perform the smart refresh if items were actually created.
        if successful_items:
            logger.info(f"Performing Smart Refresh with {len(successful_items)} new item(s).")
            if self.context == CONTEXT_OBJECTLIST:
                self.list_refresh_requested.emit()
            else:
                newly_created_skeletons = [FolderItem(**item_data) for item_data in successful_items]
                self.master_list.extend(newly_created_skeletons)
                self.apply_filters_and_search()


    def retry_creation_with_password(self, task: dict, password: str):
        """
        [NEW] Re-runs a single creation task, this time providing the password.
        """
        if not self.current_path: return

        logger.info(f"Retrying creation for '{task['source_path'].name}' with a password.")
        self.bulk_operation_started.emit()

        # The workflow service will now need to accept an optional password
        worker = Worker(
            self.workflow_service.execute_creation_workflow,
            [task], # Pass as a list with one item
            self.current_path,
            [False], # New cancel flag
            password=password # Pass the password as a keyword argument
        )
        worker.signals.result.connect(self._on_creation_finished)
        # ... (connect other signals)
        QThreadPool.globalInstance().start(worker)

    def _on_randomize_finished(self, result: dict):
        """Handles the result of a randomize operation (Flow 6.2.B)."""
        pass

    def get_thumbnail(
        self, item_id: str, source_path: Path | None, default_type: str
    ) -> QPixmap:
        """
        Flow 2.4, Step 2: A wrapper method that delegates the thumbnail request to the service.
        This decouples the View from having to know about the ThumbnailService directly.
        """
        return self.thumbnail_service.get_thumbnail(
            item_id=item_id, source_path=source_path, default_type=default_type
        )

    def get_initial_name(self, name: str):
        """
        Generates an initial from the name for avatar display.
        """
        return self.system_utils.get_initial_name(name, length=2)

    def _on_thumbnail_generated(self, item_id: str, cache_path: Path):
        """
        Receives a signal from ThumbnailService when a new thumbnail is ready on disk.
        Updates the internal item model and triggers a targeted UI refresh.
        """

        try:
            # 1. Find the appropriate item in Master_list

            item_to_update = next(
                item for item in self.master_list if item.id == item_id
            )
            if not item_to_update:
                logger.warning(
                    f"Item '{item_id}' no longer in list when its thumbnail was ready."
                )
                return

            updated_item = item_to_update

            # ---Revised Logic: Check Item Type Before Updating ---
            # 2. Only update the model if it is Objectitem

            if isinstance(item_to_update, ObjectItem):
                # Update the thumbnail_path to point to the new cache file.
                # This helps in case of a full refresh, it can load from cache directly.

                updated_item = dataclasses.replace(
                    item_to_update, thumbnail_path=cache_path
                )

                # Replace the old item with the new one in the internal state

                master_idx = self.master_list.index(item_to_update)
                self.master_list[master_idx] = updated_item

                if item_to_update in self.displayed_items:
                    display_idx = self.displayed_items.index(item_to_update)
                    self.displayed_items[display_idx] = updated_item

            # For FolderItem, we don't need to change the model. The fact that the
            # thumbnail exists in the cache is enough. We just need to trigger a UI update.

            # 4. Use the existing 'item_needs_update' signal to trigger UI refresh
            #    targeted to just one widget.

            view_data = self._create_dict_from_item(updated_item)
            self.item_needs_update.emit(view_data)

        except (StopIteration, ValueError):
            logger.warning(
                f"Item '{item_id}' not found in list when its thumbnail was ready. It may have been unloaded."
            )

    def set_category_filter(self, category: ModType):
        """
        Sets the main category filter for the objectlist and re-applies all filters.
        This is the entry point called from the main orchestrator (MainWindowViewModel).
        """
        # Only apply this logic for the objectlist context
        if self.context != "objectlist" or self.active_category_filter == category:
            return

        logger.info(f"Setting category filter to '{category.value}'")
        self.active_category_filter = category

        # In Stage 3, we will add a signal here to rebuild the filter UI
        self._update_available_filters()

        # Trigger a full view update with the new category filter applied
        self.apply_filters_and_search()

    def _update_available_filters(self):
        """
        [REVISED for ALIAS] Generates available filter options and their
        display names (aliases) based on the game's schema.
        """
        if not self.current_game or not self.current_game.game_type:
            self.available_filters_changed.emit({})
            return

        game_type = self.current_game.game_type
        # The new structure for available_options will be:
        # { 'internal_key': ('DisplayName', [option1, option2]), ... }
        available_options = {}

        if self.context == CONTEXT_OBJECTLIST:
            schema = self.database_service.get_schema_for_game(game_type)
            if not schema:
                self.available_filters_changed.emit({})
                return

            logger.info(f"Generating aliased filter options for 'objectlist' (Game: {game_type}).")

            if self.active_category_filter == ModType.CHARACTER:
                # Define which keys from the schema we want to create filters for
                filter_keys = ["rarity", "element", "gender", "weapon_types"]
                for key in filter_keys:
                    options = schema.get(key, [])
                    if options:
                        # Get the alias for the key, e.g., 'element' -> 'Combat Type'
                        display_name = self.database_service.get_alias_for_game(game_type, key)
                        available_options[key] = (display_name, options)
            else: # For 'Other' categories
                # You can add similar alias logic for subtypes if needed
                all_subtypes = set(i.subtype for i in self.master_list if isinstance(i, GenericObjectItem) and i.subtype)
                if all_subtypes:
                    display_name = self.database_service.get_alias_for_game(game_type, "subtype", fallback="Subtype")
                    available_options['subtype'] = (display_name, sorted(list(all_subtypes)))

        elif self.context == CONTEXT_FOLDERGRID:
            # (Logika untuk foldergrid tetap sama karena tidak menggunakan alias dari schema)
            all_authors = set(i.author for i in self.master_list if isinstance(i, FolderItem) and i.author)
            all_tags = set()
            for item in self.master_list:
                if isinstance(item, FolderItem) and item.tags:
                    all_tags.update(item.tags)
            if all_authors:
                available_options['author'] = ("Author", sorted(list(all_authors)))
            if all_tags:
                available_options['tags'] = ("Tags", sorted(list(all_tags)))

        self.available_filters_changed.emit(available_options)

    def clear_all_filters_and_search(self):
        """Clears all active filters and the search query."""
        should_update = bool(self.active_filters or self.search_query)

        self.active_filters = {}
        self.search_query = ""

        # If there was something to clear, trigger a UI update
        if should_update:
            logger.info("Clearing all filters and search.")
            # Also notify the view to clear the search bar text
            self.clear_search_text.emit()
            self.apply_filters_and_search()

    def _on_creation_progress_updated(self, current, total):
        """Handles progress updates during the object creation workflow."""
        # This is a placeholder for any UI updates or logging.
        # You can connect this to a progress bar or similar UI element.
        logger.debug(f"Creation progress: {current}/{total}")
        pass

    def _on_creation_error(self, error_info: tuple):
        """Handles a critical failure during the creation worker thread."""
        exctype, value, tb = error_info
        logger.critical(f"A worker error occurred during object creation: {value}\n{tb}")

        self.bulk_operation_finished.emit([])

        self.toast_requested.emit(
            "A critical error occurred during creation. Please check the logs.", "error"
        )

    def initiate_reconciliation(self):
        """
        [NEW in Step 2] Gathers all local and database objects and starts the
        background reconciliation workflow in WorkflowService.
        """
        # 1. Validate that there is an active game with a valid game_type
        if not self.current_game or not self.current_game.game_type:
            self.toast_requested.emit(
                "Cannot sync: Active game has no Database Key (Type) set.", "warning"
            )
            return

        game_type = self.current_game.game_type
        game_path = self.current_game.path
        logger.info(f"Initiating database reconciliation for game_type: '{game_type}'")

        # 2. Gather all required data
        all_local_items = self.master_list
        all_db_objects = self.database_service.get_all_objects_for_game(game_type)

        if not all_db_objects:
            self.toast_requested.emit(f"No objects defined in the database for '{game_type}'. Nothing to sync.", "info")
            return

        # 3. Start the background worker targeting the new WorkflowService method
        self.bulk_operation_started.emit()
        worker = Worker(
            self.workflow_service.reconcile_objects_with_database,
            game_path,
            game_type,
            all_local_items,
            all_db_objects
        )
        worker.signals.result.connect(self._on_reconciliation_finished)
        worker.signals.error.connect(
            lambda err: self._on_generic_worker_error(None, err, "reconciliation")
        )
        # You can also connect the progress signal if your service emits it
        worker.signals.progress.connect(self.reconciliation_progress_updated)

        QThreadPool.globalInstance().start(worker)

    # --- ADD a new slot to handle the result of the new workflow ---
    def _on_reconciliation_finished(self, result: dict):
        """
        [NEW in Step 2] Handles the summary result from the reconciliation workflow.
        """
        self.bulk_operation_finished.emit(result.get("failures", []))

        if result.get("success"):
            created = result.get("created", 0)
            updated = result.get("updated", 0)
            failed = result.get("failed", 0)

            # Build a summary message
            summary = f"Reconciliation complete: {created} created, {updated} updated."
            if failed > 0:
                summary += f" ({failed} failed)."
                self.toast_requested.emit(summary, "warning")
            else:
                self.toast_requested.emit(summary, "success")
        else:
            self.toast_requested.emit("Reconciliation process failed to run.", "error")

        # Always refresh the list to show the final state
        self.list_refresh_requested.emit()


    def get_current_game_schema(self) -> dict | None:
        """
        A helper for the View to get the schema for the currently
        active game using its 'game_type' for the lookup.
        """
        # --- STAGE 1: Validate active game ---
        if not self.current_game:
            logger.warning("get_current_game_schema called but no active game.")
            return None

        # --- STAGE 2: Validate game_type ---
        game_type_to_lookup = self.current_game.game_type

        if not game_type_to_lookup:
            logger.warning(
                f"Cannot get schema: Active game '{self.current_game.name}' has no game_type set."
            )
            # --- The Core Change ---
            # Instead of just failing, ask the UI to fix this configuration issue.
            logger.info(f"Emitting signal to request setup for game ID: {self.current_game.id}")
            self.game_type_setup_required.emit(self.current_game.id)
            # ---------------------
            return None # Still return None to stop the current operation

        # --- STAGE 3: Fetch schema using the valid game_type ---
        logger.info(f"Requesting schema for game_type: '{game_type_to_lookup}'")
        return self.database_service.get_schema_for_game(game_type_to_lookup)

    def convert_object_type(self, item_id: str, new_type: ModType):
        """
        Initiates the background process to convert an object's type.
        """
        item_to_convert = next((item for item in self.master_list if item.id == item_id), None)

        if not item_to_convert:
            logger.error(f"Cannot convert type: Item with ID '{item_id}' not found.")
            return

        logger.info(f"Request to convert '{item_to_convert.actual_name}' to type '{new_type.value}'.")

        self.item_processing_started.emit(item_id)

        worker = Worker(
            self.mod_service.convert_object_type,
            item_id,
            item_to_convert.folder_path,
            new_type.value
        )

        # --- FINAL STEP: Connect signals to handle the result ---
        worker.signals.result.connect(self._on_conversion_finished)
        worker.signals.error.connect(
            lambda error_info, id=item_id: self._on_conversion_error(error_info, id)
        )

        QThreadPool.globalInstance().start(worker)

    def _on_conversion_finished(self, result: dict):
        """
        [IMPLEMENTED] Handles the result of the conversion process.
        Reloads the entire object list on success to reflect model changes.
        """
        item_id = result.get("item_id")

        # Always signal that processing is finished for this item
        if item_id:
            self.item_processing_finished.emit(item_id, result["success"])

        if result.get("success"):
            logger.info(f"Type conversion successful for item {item_id}. Reloading object list.")
            self.toast_requested.emit("Object type converted successfully.", "success")

            # TODO: 1. Find the name of the item to re-select after the refresh
            item_to_reselect = next((item for item in self.master_list if item.id == item_id), None)
            item_id_to_select = item_to_reselect.id if item_to_reselect else None
            if item_id_to_select:
                logger.info(f"Item to re-select after reload: {item_to_reselect.actual_name}")

            # 2. Emit a signal requesting the parent ViewModel to handle the reload
            self.list_refresh_requested.emit()

        else:
            # On failure, show an error toast
            self.toast_requested.emit(f"Failed to convert type: {result.get('error')}", "error")

    def _on_conversion_error(self, error_info: tuple, item_id: str):
        """
        [NEW] Handles a critical failure during the conversion worker thread.
        """
        exctype, value, tb = error_info
        logger.critical(f"A worker error occurred during type conversion for item {item_id}: {value}\n{tb}")

        # Ensure the UI is unblocked
        self.item_processing_finished.emit(item_id, False)

        # Show a generic error message to the user
        self.toast_requested.emit("A critical error occurred. Please check the logs.", "error")


    def activate_mod_exclusively(self, item_id_to_activate: str):
        """
        [NEW] Starts the "Enable Only This" workflow. It finds which mods
        need to be disabled and requests confirmation from the user via a signal.
        """
        if self.context != CONTEXT_FOLDERGRID:
            return

        item_to_enable = next((i for i in self.master_list if i.id == item_id_to_activate), None)
        if not item_to_enable or item_to_enable.status == ModStatus.ENABLED:
            return

        # Find all other mods in the current list that are already enabled
        items_to_disable = [
            item for item in self.master_list
            if item.id != item_id_to_activate and item.status == ModStatus.ENABLED
        ]

        # Create an action plan
        action_plan = {
            "enable": item_to_enable,
            "disable": items_to_disable,
            "enable_name": item_to_enable.actual_name,
            "disable_names": [i.actual_name for i in items_to_disable]
        }

        # If there's nothing to disable, we don't need to ask for confirmation.
        # We can proceed directly.
        if not items_to_disable:
            logger.info(f"No other mods to disable. Proceeding to enable '{item_to_enable.actual_name}'.")
            self.proceed_with_exclusive_activation(action_plan)
        else:
            # If there are mods to disable, ask the user for confirmation first.
            logger.info("Requesting user confirmation for exclusive activation.")
            self.exclusive_activation_confirmation_requested.emit(action_plan)

    def proceed_with_exclusive_activation(self, plan: dict):
        """
        [NEW] Called by the View after the user confirms the action.
        This method starts the background worker.
        """
        item_to_enable = plan.get("enable")
        if not item_to_enable:
            return

        logger.info(f"User confirmed. Starting exclusive activation for '{item_to_enable.actual_name}'.")

        # Emit a signal to show a global loading indicator/lock the UI
        self.bulk_operation_started.emit()

        worker = Worker(self.workflow_service.execute_exclusive_activation, plan)
        worker.signals.result.connect(self._on_exclusive_activation_finished)
        # We can create a generic error handler for these workers later
        # worker.signals.error.connect(...)

        QThreadPool.globalInstance().start(worker)

    def _on_exclusive_activation_finished(self, result: dict):
        """
        [NEW] Handles the result from the exclusive activation workflow.
        """
        # Unlock the UI
        self.bulk_operation_finished.emit([]) # Send empty list for no failures

        if result.get("success"):
            self.toast_requested.emit("Mod successfully activated.", "success")
            # Request a full refresh to ensure the UI is in sync
            self.list_refresh_requested.emit()
        else:
            self.toast_requested.emit(f"Operation failed: {result.get('error')}", "error")
            # Also request a refresh in case of partial failure, to show the real state
            self.list_refresh_requested.emit()

    def force_sync_with_selection(self, item_id: str, selected_db_data: dict):
        """
        [NEW] Initiates a sync operation with a specific database entry
        chosen manually by the user.
        """
        item_to_sync = next((item for item in self.master_list if item.id == item_id), None)
        if not item_to_sync:
            logger.error(f"Cannot force sync: Item with ID '{item_id}' not found.")
            return

        logger.info(f"User forced sync for '{item_to_sync.actual_name}' with DB entry '{selected_db_data.get('name')}'.")

        self.item_processing_started.emit(item_id)
        worker = Worker(self.mod_service.update_object_properties_from_db, item_to_sync, selected_db_data)
        worker.signals.result.connect(self._on_sync_finished)
        QThreadPool.globalInstance().start(worker)

    def initiate_sync_for_item(self, item_id: str):
        """
        [NEW] Starts the sync workflow for a single item. It finds the best
        match and decides whether to sync automatically or ask for user input.
        """
        if not self.current_game or not self.current_game.game_type:
            self.toast_requested.emit("Cannot sync: Active game has no Database Key (Type) set.", "error")
            return

        item_to_sync = next((item for item in self.master_list if item.id == item_id), None)
        if not item_to_sync:
            logger.error(f"Cannot sync: Item with ID '{item_id}' not found.")
            return

        game_type = self.current_game.game_type
        item_name = item_to_sync.actual_name

        logger.info(f"Initiating sync for '{item_name}'. Finding best match in database...")

        # --- THE CORE FIX ---
        # 1. Fetch the list of all DB objects ONCE.
        all_db_objects = self.database_service.get_all_objects_for_game(game_type)

        # 2. Pass the pre-fetched list to the matching method.
        best_match_info = self.database_service.find_best_object_match(all_db_objects, item_name)
        # --- END OF FIX ---

        # 2. Core Logic: Decide what to do
        if best_match_info and best_match_info.get("score", 0) > 0.75:
            # High confidence match: Proceed with auto-sync
            db_data = best_match_info["match"]
            logger.info(f"High confidence match found: '{db_data.get('name')}' with score {best_match_info['score']:.2f}. Proceeding with auto-sync.")
            self.item_processing_started.emit(item_id)
            worker = Worker(self.mod_service.update_object_properties_from_db, item_to_sync, db_data)
            worker.signals.result.connect(self._on_sync_finished)
            QThreadPool.globalInstance().start(worker)
        else:
            # Low confidence match or no match: Request manual user selection
            logger.info("Low confidence match or no match found. Requesting manual user selection.")
            all_candidates = self.database_service.get_all_objects_for_game(game_type)
            self.manual_sync_required.emit(item_id, all_candidates)

    def _on_sync_finished(self, result: dict):
        """
        [NEW] Handles the result of a sync operation.
        """
        item_id = result.get("item_id")
        if not item_id: return

        self.item_processing_finished.emit(item_id, result.get("success", False))

        if result.get("success"):
            self.toast_requested.emit("Sync with database successful.", "success")
            self.thumbnail_service.invalidate_cache(item_id)
            self.list_refresh_requested.emit()
        else:
            self.toast_requested.emit(f"Sync failed: {result.get('error')}", "error")


    def update_object_item(self, item_id: str, update_data: dict):
        """
        [NEW] Initiates the background process to update an object's properties.
        """
        if item_id in self._processing_ids:
            return

        item_to_update = next((item for item in self.master_list if item.id == item_id), None)
        if not item_to_update:
            logger.error(f"Cannot update: Item with ID '{item_id}' not found.")
            return

        logger.info(f"Request to update object '{item_to_update.actual_name}'.")
        self._processing_ids.add(item_id)
        self.item_processing_started.emit(item_id)

        worker = Worker(self.mod_service.update_object, item_to_update, update_data)
        worker.signals.result.connect(self._on_update_finished)
        # Tambahkan penanganan error untuk robusta
        worker.signals.error.connect(lambda err, id=item_id: self._on_generic_worker_error(id, err, "update"))

        QThreadPool.globalInstance().start(worker)

    def _on_update_finished(self, result: dict):
        """
        [NEW] Handles the result of the object update operation.
        """
        item_id = result.get("item_id")
        if not item_id: return

        self._processing_ids.discard(item_id)
        self.item_processing_finished.emit(item_id, result.get("success", False))

        if result.get("success"):
            self.toast_requested.emit("Object updated successfully.", "success")
            # Request a full refresh to ensure the UI is in sync
            self.thumbnail_service.invalidate_cache(item_id)
            self.toast_requested.emit("Object updated successfully.", "success")
            self.list_refresh_requested.emit()
        else:
            self.toast_requested.emit(f"Update failed: {result.get('error')}", "error")

    def _on_generic_worker_error(self, item_id: str, error_info: tuple, action: str):
        """Generic handler for critical worker failures."""
        self._processing_ids.discard(item_id)
        self.item_processing_finished.emit(item_id, False)

        exctype, value, tb = error_info
        logger.critical(f"A worker error occurred during '{action}' for item {item_id}: {value}\n{tb}")
        self.toast_requested.emit(f"A critical error occurred during {action}. Please check logs.", "error")

    def prepare_creation_tasks(self, paths: List[Path]):
        """
        [NEW] Starts a light background worker to analyze a list of source paths
        (folders/archives) before showing the confirmation dialog.
        """
        if not paths:
            return

        self.toast_requested.emit(f"Analyzing {len(paths)} item(s)...", "info")
        logger.info(f"Preparing creation tasks for {len(paths)} source path(s).")

        worker = Worker(self.workflow_service.analyze_creation_sources, paths)
        self._active_workers.append(worker)
        worker.signals.result.connect(
            lambda result: self._on_tasks_analyzed(result, worker)
        )

        # This will handle the result of the analysis and emit the final signal
        worker.signals.error.connect(
            lambda err, w=worker: self._on_generic_worker_error(None, err, "analysis")
        )



        QThreadPool.globalInstance().start(worker)

    def _analyze_paths_in_worker(self, paths: List[Path]) -> list:
        """
        [NEW] Private method that runs in the worker thread to perform the analysis.
        """
        logger.info(f"Analyzing {paths} source paths for mod creation tasks.")
        valid_tasks = []
        invalid_items = []
        for path in paths:
            task_info = self.mod_service.analyze_source_path(path)
            if task_info["is_valid"]:
                valid_tasks.append(task_info)
                logger.info(f"Valid task found: {path.name}")
            else:
                # Instead of emitting a signal, just collect the invalid items
                error_msg = task_info.get('error_message', 'Invalid item')
                invalid_items.append({"name": path.name, "reason": error_msg})
                logger.warning(f"Invalid task found: {path.name} - {error_msg}")

        # Return a dictionary with both lists
        logger.info(f"Analysis complete. Valid tasks: {len(valid_tasks)}, Invalid items: {len(invalid_items)}")
        return {"valid": valid_tasks, "invalid": invalid_items}

    def _on_tasks_analyzed(self, result: dict, worker: Worker):
        """
        [REVISED] This slot now receives a dictionary, shows toasts for invalid
        items, and then emits the signal for valid tasks.
        """
        logger.info(f"Analysis finished. Valid tasks: {len(result.get('valid', []))}, Invalid items: {len(result.get('invalid', []))}")
        # 1. Remove the worker from the active list to prevent memory leaks
        if worker in self._active_workers:
            self._active_workers.remove(worker)

        # 2. Show toasts for any items that were skipped
        invalid_items = result.get("invalid", [])
        for item in invalid_items:
            self.toast_requested.emit(f"Skipped '{item['name']}': {item['reason']}", "warning")

        # 3. Emit the final signal with only the valid tasks
        valid_tasks = result.get("valid", [])
        self.creation_tasks_prepared.emit(valid_tasks)

    def start_background_creation(self, tasks: list, cancel_flag: list, progress_signal: pyqtSignal, finished_signal: pyqtSignal):
        """
        [NEW] Starts the background worker for mod creation.
        Receives a cancel_flag and progress/finished signals from the View's dialog.
        """
        if not tasks:
            logger.warning("No valid tasks provided for background creation.")
            return


        logger.info(f"Starting background creation of {len(tasks)} mods.")

        # The ViewModel emits this to tell the main window to disable itself
        self.bulk_operation_started.emit()

        worker = Worker(
            self.workflow_service.execute_creation_workflow,
            tasks,
            self.current_path,
            cancel_flag=cancel_flag
        )

        # Connect worker signals
        worker.signals.result.connect(
            lambda result, tasks_info=tasks: self._on_creation_finished(result, tasks_info)
        )
        worker.signals.error.connect(lambda err, t=tasks: self._on_creation_error(err))
        # Connect worker's progress directly to the dialog's progress signal
        worker.signals.progress.connect(progress_signal)
        # When the worker is truly finished, also emit the dialog's finished signal
        worker.signals.finished.connect(finished_signal)

        self._active_workers.append(worker)
        QThreadPool.globalInstance().start(worker)


