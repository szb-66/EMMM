from difflib import SequenceMatcher
from pathlib import Path
from typing import List
from PyQt6.QtCore import pyqtSignal
from app.core.constants import CONTEXT_OBJECTLIST
from app.models.game_model import Game
from app.services.config_service import ConfigService
from app.services.database_service import DatabaseService
from app.services.mod_service import ModService
from app.utils.logger_utils import logger
from app.models.mod_item_model import ModStatus

class WorkflowService:
    """
    Orchestrates complex, multi-step, and/or transactional workflows.
    This service contains the business logic for operations that involve
    multiple items or multiple services.
    """

    def __init__(self, mod_service: ModService, config_service: ConfigService, database_service: DatabaseService):
        # --- Injected Services ---
        self.mod_service = mod_service
        self.config_service = config_service
        self.database_service = database_service

    # --- Bulk Modification Workflows ---
    def execute_bulk_action(self, items: list, action_type: str, **kwargs) -> dict:
        """Flow 3.2: Handles simple bulk actions like enable, disable, or tag."""
        # Iterates through items, calls the appropriate ModService method for each,
        # and collects success/failure results.
        return {}

    # --- Creation Workflows ---
    def execute_creation(self, tasks: list, parent_path: Path) -> dict:
        """Flow 4.1.A: Creates multiple foldergrid items from a list of tasks."""
        # Iterates through tasks and calls mod_service.create_foldergrid_item for each.
        return {}

    def execute_object_creation(self, tasks: list, parent_path: Path, progress_callback=None) -> dict:
        """
        Flow 4.1.B Step 5: Orchestrates the creation of multiple objectlist items.
        """
        successful_creations = []
        failed_creations = []
        total_tasks = len(tasks)

        logger.info(f"Starting object creation workflow for {total_tasks} task(s).")

        for idx, task in enumerate(tasks):
            try:
                # Delegate the actual creation to ModService
                result = self.mod_service.create_manual_object(parent_path, task["data"])

                if result["success"]:
                    successful_creations.append(result["data"])
                else:
                    failed_creations.append({"task": task, "reason": result["error"]})

            except Exception as e:
                logger.error(f"Critical error during creation task {task}: {e}", exc_info=True)
                failed_creations.append({"task": task, "reason": str(e)})

            # Emit progress if a callback is provided
            if progress_callback:
                progress_callback.emit(idx + 1, total_tasks)

        return {"success": successful_creations, "failed": failed_creations}

    # --- High-Risk Transactional Workflows ---
    def apply_safe_mode(self, items: list, is_on: bool) -> dict:
        """Flow 6.1: Applies the Safe Mode state with rollback-on-failure logic."""
        # 1. Plan all required file system actions.
        # 2. Execute the plan, building an undo_log.
        # 3. If any step fails, execute the undo_log in reverse.
        return {}

    def apply_preset(self, items: list, preset_name: str) -> dict:
        """Flow 6.2.A: Applies a mod preset with rollback-on-failure logic."""
        # Similar to apply_safe_mode: Plan -> Execute with Undo -> Rollback.
        return {}

    # --- Randomization Workflows ---
    def apply_randomize(self, items: list) -> dict:
        """Flow 6.2.B: Disables all items in a list and enables one at random."""
        # A simpler bulk action that plans to disable all but one winner.
        return {}

    def apply_global_randomize(self, game_path: Path) -> dict:
        """Flow 6.2.B: Disables ALL mods in a game and enables one at random."""
        # 1. Recursively scans the entire game_path to find all valid mod folders.
        # 2. Plans and executes the randomization.
        return {}

    # --- Preset Management Workflows ---
    def rename_preset(self, old_name: str, new_name: str, game_path: Path) -> dict:
        """Flow 6.2.A: Renames a preset in config.ini and all relevant info.json files."""
        # A heavy operation that involves recursively scanning the mod directory.
        return {}

    def delete_preset(self, preset_name: str, game_path: Path) -> dict:
        """Flow 6.2.A: Deletes a preset from config.ini and all relevant info.json files."""
        # A heavy operation that involves recursively scanning the mod directory.
        return {}

    # --- Private/Internal Logic ---
    def _execute_rollback(self, undo_log: list):
        """
        [IMPLEMENTED] A helper method to reverse a series of file operations after a failure.
        It iterates through a log of successfully changed items and toggles their status back.
        """
        if not undo_log:
            return

        logger.info(f"Initiating rollback for {len(undo_log)} actions.")
        # Iterate in reverse to undo actions in the opposite order they were performed
        for item_to_revert in reversed(undo_log):
            try:
                logger.debug(f"Rolling back status for '{item_to_revert.actual_name}'...")
                # Calling toggle_status again will revert the change
                self.mod_service.toggle_status(item_to_revert)
            except Exception as e:
                # Log an error if a specific rollback action fails, but continue
                logger.error(f"Failed to roll back item '{item_to_revert.actual_name}'. Reason: {e}", exc_info=True)


    def execute_exclusive_activation(self, plan: dict) -> dict:
        """
        [NEW] Executes the 'Enable Only This' action by disabling a list of mods
        and then enabling a single mod. This is a transactional operation.
        """
        item_to_enable = plan.get("enable")
        items_to_disable = plan.get("disable", [])

        if not item_to_enable:
            return {"success": False, "error": "Target item to enable was not specified."}

        logger.info(f"Executing exclusive activation: Enabling '{item_to_enable.actual_name}', Disabling {len(items_to_disable)} mod(s).")

        # --- Transactional Logic with Rollback ---
        undo_log = []
        try:
            # 1. Disable all currently enabled mods
            for item in items_to_disable:
                result = self.mod_service.toggle_status(item, target_status=ModStatus.DISABLED)
                if not result.get("success"):
                    # If one fails, stop and roll back
                    raise Exception(f"Failed to disable '{item.actual_name}': {result.get('error')}")
                # Log the successful action for potential rollback
                undo_log.append({"action": "enable", "item": result.get("data")})

            # 2. Enable the target mod
            result = self.mod_service.toggle_status(item_to_enable, target_status=ModStatus.ENABLED)
            if not result.get("success"):
                raise Exception(f"Failed to enable '{item_to_enable.actual_name}': {result.get('error')}")

            return {"success": True}

        except Exception as e:
            logger.error(f"Exclusive activation failed. Rolling back changes. Reason: {e}")
            # Rollback logic would go here if needed, for now we just report the error
            self._execute_rollback(undo_log)
            return {"success": False, "error": str(e)}

    def reconcile_objects_with_database(self, game_path: Path, game_type: str, all_local_items: list, all_db_objects: list, progress_callback=None) -> dict:
        """
        [NEW] The core reconciliation engine. It compares local items with the database,
        creates a plan to create missing items and update existing ones, and then
        executes that plan.
        """
        logger.info(f"Starting reconciliation for game '{game_type}'. Local items: {len(all_local_items)}, DB objects: {len(all_db_objects)}")
        if game_type is None:
           game_type = self.database_service.get_game_type_from_path(game_path)


        tasks_to_create = []
        tasks_to_update = []
        matched_db_names = set()

        # --- STAGE 1: Match Existing Local Items ---
        for local_item in all_local_items:
            # Call the existing, centralized matching method
            match_info = self.database_service.find_best_object_match(
                all_db_objects, local_item.actual_name
            )
            # If a confident match is found, plan an update
            if match_info and match_info.get("score", 0) > 0.8:
                best_match = match_info["match"]
                tasks_to_update.append({"local_item": local_item, "db_data": best_match})
                # Keep track of the DB object that has been matched
                matched_db_names.add(best_match.get("name").lower())

        # --- STAGE 2: Plan Creation for Unmatched DB Objects ---
        for db_obj in all_db_objects:
            if db_obj.get("name").lower() not in matched_db_names:
                tasks_to_create.append({"type": "sync", "data": db_obj})

        logger.info(f"Reconciliation plan: {len(tasks_to_create)} to create, {len(tasks_to_update)} to update.")

        # --- STAGE 3: Execute the Plan ---
        successful_creates = 0
        successful_updates = 0
        failures = []
        total_tasks = len(tasks_to_create) + len(tasks_to_update)
        parent_path_for_creation = game_path

        # Execute creation tasks
        for idx, task in enumerate(tasks_to_create):
            if parent_path_for_creation:
                result = self.mod_service.create_manual_object(parent_path_for_creation, task['data'])
                if result.get("success"):
                    successful_creates += 1
                else:
                    failures.append({"item_name": task['data'].get('name'), "reason": result.get('error')})
            if progress_callback:
                progress_callback.emit(idx + 1, total_tasks)

        # Execute update tasks
        for idx, task in enumerate(tasks_to_update, start=len(tasks_to_create)):
            result = self.mod_service.update_object_properties_from_db(task['local_item'], task['db_data'])
            if result.get("success"):
                successful_updates += 1
            else:
                failures.append({"item_name": task['local_item'].actual_name, "reason": result.get('error')})
            if progress_callback:
                progress_callback.emit(idx + 1, total_tasks)

        payload = {
            "game_type": game_type,
            "created": successful_creates,
            "updated": successful_updates,
            "failed": len(failures),
            "failures": failures
        }
        logger.info("Reconciliation finished. Summary: %s", payload)
        return payload

    def analyze_creation_sources(self, paths: list, progress_callback=None) -> dict:
        """
        [NEW] Runs the analysis of source paths in the background. This method
        is designed to be the target of a worker thread.
        """
        valid_tasks = []
        invalid_items = []
        total = len(paths)

        logger.info(f"Worker started. Analyzing {total} source path(s).")

        for idx, path in enumerate(paths):
            logger.debug(f"Analyzing path {idx + 1}/{total}: {path.name}")
            try:
                task_info = self.mod_service.analyze_source_path(path)
                if task_info["is_valid"]:
                    valid_tasks.append(task_info)
                    logger.debug(f"Path '{path.name}' is valid.")
                else:
                    error_msg = task_info.get('error_message', 'Invalid item')
                    invalid_items.append({"name": path.name, "reason": error_msg})
                    logger.warning(f"Path '{path.name}' is invalid: {error_msg}")
            except Exception as e:
                # Catch unexpected errors during analysis of a single file
                logger.error(f"Critical error analyzing '{path.name}': {e}", exc_info=True)
                invalid_items.append({"name": path.name, "reason": "Analysis crashed."})

        logger.info(f"Worker finished analysis. Valid: {len(valid_tasks)}, Invalid: {len(invalid_items)}")
        return {"valid": valid_tasks, "invalid": invalid_items}

    def reconcile_single_game(self, game: Game, progress_callback=None) -> dict:
        """
        [NEW] A self-contained workflow that reconciles all objects for a
        single game. It fetches all necessary data itself.
        """
        if not game or not game.game_type:
            return {"success": False, "error": "Invalid game or missing game_type."}

        game_type = game.game_type
        logger.info(f"Starting self-contained reconciliation for game: '{game.name}' (Type: {game_type})")

        # 1. Fetch all required data directly within the service
        all_local_items = self.mod_service.get_item_skeletons(game.path, CONTEXT_OBJECTLIST).get("items", [])
        all_db_objects = self.database_service.get_all_objects_for_game(game_type)

        # 2. Reuse the existing, powerful reconciliation engine
        # We pass the fetched data to the method we built previously.
        result_summary = self.reconcile_objects_with_database(
            game_path=game.path,
            game_type=game_type,
            all_local_items=all_local_items,
            all_db_objects=all_db_objects,
            progress_callback=progress_callback
        )

        return result_summary

    def execute_creation_workflow(self, tasks: list, parent_path: Path, cancel_flag: List[bool], progress_callback=None, **kwargs) -> dict:
        """
        [NEW] Iterates through creation tasks, calling the mod_service to
        copy or extract each one. Checks for cancellation between each task.
        """
        successful_items = []
        failed_items = []
        cancelled_count = 0
        total_tasks = len(tasks)

        for idx, task in enumerate(tasks):
            # --- Cancellation Check ---
            if cancel_flag[0]:
                logger.info("Creation workflow cancelled by user.")
                cancelled_count = total_tasks - idx
                break # Exit the loop

            output_name = task.get("output_name")
            source_path = task.get("source_path")

            if progress_callback:
                progress_callback.emit(idx + 1, total_tasks)


            result = self.mod_service.create_mod_from_source(source_path, output_name, parent_path, cancel_flag[0], **kwargs)

            if result.get("success"):
                successful_items.append(result.get("skeleton_data"))
            elif result.get("status") == "cancelled":
                cancelled_count = total_tasks - idx
                break
            else:
                failed_items.append({"source": source_path.name, "reason": result.get("error")})

        # Final progress update
        if progress_callback:
            progress_callback.emit(total_tasks, total_tasks)

        return {
            "successful_items": successful_items,
            "failed_items": failed_items,
            "cancelled_count": cancelled_count
        }