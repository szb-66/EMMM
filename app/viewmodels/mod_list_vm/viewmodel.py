# App/viewmodels/mod list vm.py


import dataclasses
from pathlib import Path
from typing import List
from PyQt6.QtCore import QObject, pyqtSignal, QThreadPool, QTimer
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

from app.viewmodels.mod_list_vm._load_mixin import _LoadMixin
from app.viewmodels.mod_list_vm._filter_mixin import _FilterMixin


from app.viewmodels.mod_list_vm._crud_mixin import _CrudMixin
from app.viewmodels.mod_list_vm._creation_mixin import _CreationMixin
from app.viewmodels.mod_list_vm._reconciliation_mixin import _ReconciliationMixin
from app.viewmodels.mod_list_vm._exclusive_activation_mixin import _ExclusiveActivationMixin
from app.viewmodels.mod_list_vm._thumbnail_mixin import _ThumbnailMixin


class ModListViewModel(_ThumbnailMixin, _ExclusiveActivationMixin,
                      _ReconciliationMixin, _CreationMixin, _CrudMixin,
                      _FilterMixin, _LoadMixin, QObject):
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

    def initiate_randomize(self):
        """Flow 6.2.B: Starts the randomization workflow for the current group."""
        pass

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

    def _on_bulk_action_finished(self, result: dict):
        """Handles the result of a bulk action like enable, disable, or tag (Flow 3.2)."""
        pass

    def _on_randomize_finished(self, result: dict):
        """Handles the result of a randomize operation (Flow 6.2.B)."""
        pass

    def _on_generic_worker_error(self, item_id: str, error_info: tuple, action: str):
        """Generic handler for critical worker failures."""
        self._processing_ids.discard(item_id)
        self.item_processing_finished.emit(item_id, False)

        exctype, value, tb = error_info
        logger.critical(f"A worker error occurred during '{action}' for item {item_id}: {value}\n{tb}")
        self.toast_requested.emit(f"A critical error occurred during {action}. Please check logs.", "error")

