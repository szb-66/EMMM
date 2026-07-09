# app/viewmodels/mod_list_vm/_exclusive_activation_mixin.py
"""'Enable Only This' exclusive-activation workflow.

Extracted from the original monolithic ``mod_list_vm.py`` per ADR 0001.
The Mixin must NOT define ``__init__`` or any ``pyqtSignal``.
"""
from PyQt6.QtCore import QThreadPool

from app.models.mod_item_model import ModStatus
from app.utils.async_utils import Worker
from app.utils.logger_utils import logger
from app.core.constants import CONTEXT_FOLDERGRID


class _ExclusiveActivationMixin:
    # --- 'Enable Only This' exclusive activation ---

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

