# app/viewmodels/mod_list_vm/_creation_mixin.py
"""Object-creation workflow + drag-drop archive import.

Extracted from the original monolithic ``mod_list_vm.py`` per ADR 0001.
The Mixin must NOT define ``__init__`` or any ``pyqtSignal``.
"""
from pathlib import Path
from typing import List

from PyQt6.QtCore import QThreadPool, pyqtSignal

from app.models.mod_item_model import FolderItem, ModStatus
from app.utils.async_utils import Worker
from app.utils.logger_utils import logger
from app.core.constants import CONTEXT_OBJECTLIST
from app.core import i18n as _i18n


class _CreationMixin:
    # --- Object creation + archive import workflows ---

    def initiate_create_objects(self, tasks: list):
        """
        Flow 4.1.B Step 4: Starts the background workflow for creating new objects.
        """
        if not tasks:
            return

        if not self.current_game or not self.current_game.path.is_dir():
            self.toast_requested.emit(_i18n.tr("vm.cannot_create_no_path"), "error")
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
            self.toast_requested.emit(_i18n.tr("vm.created_success", name=object_name), "success")
            if self.context == CONTEXT_OBJECTLIST:
                self._item_to_select_after_load = object_name
                self.object_created.emit(created_object_data)
        else:
            # 1. Build the summary message
            summary_parts = []
            if successful_count > 0:
                summary_parts.append(_i18n.tr("vm.created_count", count=successful_count))
            if failed_count > 0:
                summary_parts.append(_i18n.tr("vm.failed_count", count=failed_count))
            if cancelled_count > 0:
                summary_parts.append(_i18n.tr("vm.cancelled_count", count=cancelled_count))

            logger.info(f"Creation Summary: {', '.join(summary_parts)}")
            summary_content = _i18n.tr("vm.process_finished", summary=", ".join(summary_parts))
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
            _i18n.tr("vm.create_critical"), "error"
        )

    def prepare_creation_tasks(self, paths: List[Path]):
        """
        [NEW] Starts a light background worker to analyze a list of source paths
        (folders/archives) before showing the confirmation dialog.
        """
        if not paths:
            return

        self.toast_requested.emit(_i18n.tr("vm.analyzing", count=len(paths)), "info")
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
            self.toast_requested.emit(_i18n.tr("vm.skipped", name=item['name'], reason=item['reason']), "warning")

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


