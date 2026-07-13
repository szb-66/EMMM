# app/views/dialogs/sync_selection_dialog.py

from typing import List, Dict
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QDialog, QListWidgetItem
from qfluentwidgets import ListWidget, PrimaryPushButton, PushButton, SubtitleLabel, BodyLabel, SearchLineEdit
from app.core import i18n as _i18n
from app.services.thumbnail_service import ThumbnailService
from app.views.components.sync_candidate_widget import SyncCandidateWidget
from app.services.database_service import DatabaseService

class SyncSelectionDialog(QDialog):
    """
    [REVISED] A visually rich dialog that allows the user to manually select
    the correct database entry to sync with.
    """
    EditManuallyRequest = QDialog.DialogCode.Accepted + 1

    def __init__(self, item_name: str, candidates: List[dict], game_type: str, thumbnail_service: ThumbnailService, database_service: DatabaseService, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(_i18n.tr("sync_selection.title"))
        self.setFixedWidth(500)
        self.setMinimumHeight(400)

        self.selected_candidate = None
        self.all_candidates = candidates
        self.game_type = game_type
        self.thumbnail_service = thumbnail_service
        self.database_service = database_service

        # --- UI Components ---
        title = SubtitleLabel(_i18n.tr("sync_selection.select_match", name=item_name), self)
        info = BodyLabel(_i18n.tr("sync_selection.info"), self)
        info.setWordWrap(True)

        self.search_bar = SearchLineEdit(self)
        self.search_bar.setPlaceholderText(_i18n.tr("sync_selection.search"))

        self.candidate_list = ListWidget(self)
        self.candidate_list.setAlternatingRowColors(True)
        self._populate_list(self.all_candidates)

        # Populate list with custom widgets
        for candidate in candidates:
            list_item = QListWidgetItem(self.candidate_list)
            # Pass all required services to the custom widget
            widget = SyncCandidateWidget(candidate, game_type, thumbnail_service, database_service)

            list_item.setSizeHint(widget.sizeHint())
            list_item.setData(1, candidate)

            self.candidate_list.addItem(list_item)
            self.candidate_list.setItemWidget(list_item, widget)

        self.sync_button = PrimaryPushButton(_i18n.tr("sync_selection.sync_selected"))
        self.edit_button = PushButton(_i18n.tr("sync_selection.edit_manually"))
        cancel_button = PushButton(_i18n.tr("common.cancel"))

        # --- Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.edit_button)
        button_layout.addStretch(1)
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(self.sync_button)

        main_layout.addWidget(title)
        main_layout.addWidget(info)
        main_layout.addWidget(self.search_bar)
        main_layout.addWidget(self.candidate_list, 1)
        main_layout.addLayout(button_layout)

        # --- Initial State & Connections ---
        self.sync_button.setEnabled(False)
        self.candidate_list.currentItemChanged.connect(lambda: self.sync_button.setEnabled(True))
        self.search_bar.textChanged.connect(self._on_search_changed)

        self.sync_button.clicked.connect(self._on_sync_selected)
        self.edit_button.clicked.connect(self._on_edit_manually_selected)
        cancel_button.clicked.connect(self.reject)

    def _on_sync_selected(self):
        """Stores the selected candidate data and accepts the dialog."""
        selected_item = self.candidate_list.currentItem()
        if selected_item:
            self.selected_candidate = selected_item.data(1)
            self.accept()

    def _populate_list(self, candidates_to_show: List[dict]):
        """Helper method to clear and populate the list widget with custom widgets."""
        self.candidate_list.clear()
        for candidate in candidates_to_show:
            list_item = QListWidgetItem(self.candidate_list)
            widget = SyncCandidateWidget(candidate, self.game_type, self.thumbnail_service, self.database_service)

            list_item.setSizeHint(widget.sizeHint())
            list_item.setData(1, candidate)

            self.candidate_list.addItem(list_item)
            self.candidate_list.setItemWidget(list_item, widget)

    def _on_search_changed(self, text: str):
        """Filters the candidate list based on the search text."""
        search_term = text.lower().strip()

        if not search_term:
            # If search is empty, show all candidates
            self._populate_list(self.all_candidates)
            return

        # Filter candidates whose name contains the search term
        filtered_candidates = [
            candidate for candidate in self.all_candidates
            if search_term in candidate.get("name", "").lower()
        ]

        self._populate_list(filtered_candidates)

    def _on_edit_manually_selected(self):
        """Closes the dialog with a custom result code to indicate 'edit' was chosen."""
        # QDialog.Accepted is 1, QDialog.Rejected is 0. We can use a custom code like 2.
        self.done(self.EditManuallyRequest)

    def get_selected_candidate(self) -> dict | None:
        """Returns the full dictionary of the candidate the user selected."""
        return self.selected_candidate