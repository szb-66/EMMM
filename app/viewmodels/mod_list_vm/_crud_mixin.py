# app/viewmodels/mod_list_vm/_crud_mixin.py
"""Single-item CRUD: toggle status/pin, rename, delete, open-in-explorer.

Extracted from the original monolithic ``mod_list_vm.py`` per ADR 0001.
The Mixin must NOT define ``__init__`` or any ``pyqtSignal``.
"""
from PyQt6.QtCore import QThreadPool

from app.utils.async_utils import Worker
from app.utils.logger_utils import logger
from app.core.constants import CONTEXT_OBJECTLIST, CONTEXT_FOLDERGRID
from app.core import i18n as _i18n


class _CrudMixin:
    # --- Single-item CRUD operations ---

    # --- Move / New Folder / Auto-group (DnD support) ---

    def move_item_to_folder(self, item_id: str, target_folder_path):
        """Moves a mod item into target_folder_path (a navigable folder or character root)."""
        from pathlib import Path

        if item_id in self._processing_ids:
            logger.warning(f"Item '{item_id}' already processing. Ignoring move.")
            return

        item = next((i for i in self.master_list if i.id == item_id), None)
        if not item:
            logger.error(f"move_item_to_folder: item '{item_id}' not found.")
            return

        target_path = Path(target_folder_path)
        logger.info(f"Moving '{item.actual_name}' → '{target_path}'")

        self._processing_ids.add(item_id)
        self.watched_refresh_suppression_requested.emit(self.context)
        self.item_processing_started.emit(item_id)

        worker = Worker(self.mod_service.move_item_to, item, target_path)
        worker.signals.result.connect(
            lambda result, id=item_id: self._on_move_item_finished(id, result)
        )
        worker.signals.error.connect(
            lambda err, id=item_id: self._on_generic_worker_error(id, err, "move")
        )
        QThreadPool.globalInstance().start(worker)

    def _on_move_item_finished(self, item_id: str, result: dict):
        self._processing_ids.discard(item_id)
        self.item_processing_finished.emit(item_id, result.get("success", False))

        if not result.get("success"):
            self.toast_requested.emit(result.get("error", _i18n.tr("vm.move_failed")), "error")
            return

        new_item = result.get("data")
        old_id = result.get("old_id", item_id)

        # Remove the moved item from source lists (it now lives under a new parent).
        self.master_list = [i for i in self.master_list if i.id != old_id]
        self.displayed_items = [i for i in self.displayed_items if i.id != old_id]
        self.apply_filters_and_search()
        self.toast_requested.emit(_i18n.tr("vm.moved", name=new_item.actual_name), "success")

    def create_new_folder(self, name: str):
        """Creates an empty folder in the current foldergrid path, then reloads."""
        if not self.current_path:
            logger.warning("create_new_folder: no current_path.")
            return

        from pathlib import Path

        parent_path = Path(self.current_path)
        logger.info(f"Creating new folder '{name}' in '{parent_path}'")

        self.watched_refresh_suppression_requested.emit(self.context)

        worker = Worker(self.mod_service.create_empty_folder, parent_path, name)
        worker.signals.result.connect(self._on_create_folder_finished)
        worker.signals.error.connect(
            lambda err: self._on_generic_worker_error("", err, "create folder")
        )
        QThreadPool.globalInstance().start(worker)

    def _on_create_folder_finished(self, result: dict):
        if not result.get("success"):
            self.toast_requested.emit(result.get("error", _i18n.tr("vm.create_folder_failed")), "error")
            return

        self._item_to_select_after_load = result["folder_path"].name
        self.load_items(
            path=self.current_path,
            game=self.current_game,
            is_new_root=False,
        )
        self.toast_requested.emit(_i18n.tr("vm.folder_created"), "success")

    def auto_group_items(self, item_ids: list, folder_name: str):
        """Creates a new folder and moves all items into it, then reloads."""
        if not self.current_path or not item_ids:
            return

        from pathlib import Path

        items = [i for i in self.master_list if i.id in set(item_ids)]
        if not items:
            logger.warning("auto_group_items: no valid items found.")
            return

        parent_path = Path(self.current_path)
        logger.info(f"Auto-grouping {len(items)} items into '{folder_name}' in '{parent_path}'")

        for item in items:
            self._processing_ids.add(item.id)
            self.item_processing_started.emit(item.id)
        self.watched_refresh_suppression_requested.emit(self.context)

        worker = Worker(self.mod_service.auto_group_items, items, parent_path, folder_name)
        worker.signals.result.connect(self._on_auto_group_finished)
        worker.signals.error.connect(
            lambda err: self._on_generic_worker_error("", err, "auto-group")
        )
        QThreadPool.globalInstance().start(worker)

    def _on_auto_group_finished(self, result: dict):
        moved_ids = result.pop("moved_old_ids", [])
        for mid in moved_ids:
            self._processing_ids.discard(mid)
            self.item_processing_finished.emit(mid, result.get("success", False))

        if not result.get("success"):
            self.toast_requested.emit(result.get("error", _i18n.tr("vm.autogroup_failed")), "error")
            return

        self._item_to_select_after_load = result["folder_path"].name
        self.load_items(
            path=self.current_path,
            game=self.current_game,
            is_new_root=False,
        )
        self.toast_requested.emit(_i18n.tr("vm.items_grouped"), "success")

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
        # Emit processing-finished first so the UI spinner clears on the
        # live widget before any list rebuild can replace it.
        self.item_processing_finished.emit(item_id, result.get("success", False))

        if result.get("success"):
            try:
                new_item = result.get("data")

                # Update the item in the master list
                self.update_item_in_list(new_item)

                # Re-apply filters AND sorting. The sorting logic will automatically
                # move the pinned item to the top.
                self.apply_filters_and_search()

                self.toast_requested.emit(_i18n.tr("vm.pin_updated"), "success")
            except Exception as e:
                logger.error(f"Error updating item state after pin toggle: {e}", exc_info=True)
        else:
            self.toast_requested.emit(_i18n.tr("vm.pin_update_failed", error=result.get('error')), "error")


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
            self.toast_requested.emit(result.get("error", _i18n.tr("vm.unknown_error")), "error")
            return

        new_item = result.get("data")
        self.update_item_in_list(new_item)
        self.toast_requested.emit(_i18n.tr("vm.renamed", name=new_item.actual_name), "success")

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
        self.toast_requested.emit(_i18n.tr("vm.rename_critical"), "error")

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
        self.toast_requested.emit(_i18n.tr("vm.delete_critical"), "error")

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
            self.toast_requested.emit(_i18n.tr("vm.item_not_found"), "error")
            return

        # 2. Get the folder path from the item model.
        path_to_open = item.folder_path

        # 3. Delegate the action to the utility class.
        self.system_utils.open_path_in_explorer(path_to_open)

    # ---Selection Management ---

    def _on_toggle_status_finished(self, item_id: str, result: dict):
        """
        Handles the result of a single item status toggle operation.
        This version correctly handles the full model object returned by the service.
        """
        self._processing_ids.discard(item_id)

        if not result.get("success"):
            self.toast_requested.emit(result.get("error", _i18n.tr("vm.unknown_error")), "error")
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

            # 4. Emit processing-finished BEFORE the list rebuild so the
            #    spinner clears on the live widget instead of on a freshly
            #    replaced one whose owner may already have been deleted.
            self.item_processing_finished.emit(item_id, True)

            # 5. Re-sort the displayed list so the "enabled first" rule takes
            #    effect immediately, without waiting for a filesystem event.
            try:
                self.apply_filters_and_search()
            except Exception as render_err:
                logger.error(f"apply_filters_and_search failed post-toggle: {render_err}", exc_info=True)

            # 6. Emit signals to UI for updates.
            try:
                self.item_needs_update.emit(self._create_dict_from_item(new_item))
            except Exception as emit_err:
                logger.error(f"item_needs_update emit failed post-toggle: {emit_err}", exc_info=True)

            # Emit context-specific signals for domino effects.
            try:
                if self.context == CONTEXT_OBJECTLIST:
                    self.active_object_modified.emit(new_item)
                elif self.context == CONTEXT_FOLDERGRID:
                    self.foldergrid_item_modified.emit(new_item)
            except Exception as domino_err:
                logger.error(f"Domino signal emit failed post-toggle: {domino_err}", exc_info=True)

        except Exception as e:
            logger.critical(f"Unhandled error updating item state after toggle: {e}", exc_info=True)
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
            _i18n.tr("vm.critical_check_logs"), "error"
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
            self.toast_requested.emit(_i18n.tr("vm.recycled", name=item_name), "success")

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
            self.toast_requested.emit(_i18n.tr("vm.delete_failed", error=result.get('error')), "error")


