# app/viewmodels/mod_list_vm/_reconciliation_mixin.py
"""Object reconciliation, sync, type-conversion, and object update.

Extracted from the original monolithic ``mod_list_vm.py`` per ADR 0001.
The Mixin must NOT define ``__init__`` or any ``pyqtSignal``.
"""
from PyQt6.QtCore import QThreadPool

from app.models.mod_item_model import ModType
from app.utils.async_utils import Worker
from app.utils.logger_utils import logger


class _ReconciliationMixin:
    # --- Database reconciliation, sync, conversion, and update ---

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
        Uses a targeted item update instead of a full list reload.
        """
        item_id = result.get("item_id")
        if not item_id: return

        self._processing_ids.discard(item_id)
        self.item_processing_finished.emit(item_id, result.get("success", False))

        if result.get("success"):
            updated_item = result.get("data")
            if updated_item:
                self.update_item_in_list(updated_item)
                self.toast_requested.emit("Object updated successfully.", "success")
                self.thumbnail_service.invalidate_cache(item_id)
                # Trigger single-item UI refresh, not a full list rebuild.
                self.item_needs_update.emit(self._create_dict_from_item(updated_item))
                # Domino: if the updated item is the active object, notify listeners.
                if self.context == CONTEXT_OBJECTLIST and self.last_selected_item_id == item_id:
                    self.active_object_modified.emit(updated_item)
                return
            # Fallback: if data is missing, do a full refresh.
            logger.warning(
                "Update succeeded but returned no item model. Falling back to full refresh."
            )
            self.list_refresh_requested.emit()
            return

        if not result.get("success"):
            self.toast_requested.emit(f"Update failed: {result.get('error')}", "error")

