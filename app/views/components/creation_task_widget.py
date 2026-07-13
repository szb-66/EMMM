# app/views/components/creation_task_widget.py

import re
from typing import List
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QApplication
from qfluentwidgets import LineEdit, BodyLabel, ToolButton, FluentIcon, CaptionLabel

from app.core import i18n as _i18n

class CreationTaskWidget(QWidget):
    """
    [REVISED] A widget for a single item in the ConfirmationListDialog,
    with an improved layout and inline validation feedback.
    """
    validation_changed = pyqtSignal()

    ILLEGAL_CHAR_PATTERN = re.compile(r'[\\/:*?"<>|]')

    def __init__(self, task_data: dict, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self._is_valid = True
        self.existing_names_lower: List[str] = []
        self.other_proposed_names_lower: List[str] = []

        # --- Main Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 8, 5, 8)
        main_layout.setSpacing(5)

        # --- Top Row: Source Info ---
        top_row_layout = QHBoxLayout()
        from_label = BodyLabel(_i18n.tr("creation_task.from"))
        from_label.setStyleSheet("font-weight: bold;")

        source_label = CaptionLabel(f"{task_data['source_path'].name}")
        source_label.setToolTip(str(task_data['source_path']))

        self.warning_icon = ToolButton(FluentIcon.INFO, self)
        self.warning_icon.setToolTip(_i18n.tr("creation_task.ini_warning"))
        self.warning_icon.setVisible(task_data.get("has_ini_warning", False))

        top_row_layout.addWidget(from_label)
        top_row_layout.addWidget(source_label, 1)
        top_row_layout.addWidget(self.warning_icon)
        main_layout.addLayout(top_row_layout)

        # --- Bottom Row: Name Input ---
        bottom_row_layout = QHBoxLayout()
        self.name_edit = LineEdit(self)
        self.name_edit.setText(task_data.get("proposed_name", ""))
        bottom_row_layout.addWidget(self.name_edit)
        main_layout.addLayout(bottom_row_layout)

        # --- Validation Label (Initially Hidden) ---
        self.validation_label = BodyLabel("", self)
        self.validation_label.setStyleSheet("color: #f97171; font-size: 12px; padding-left: 5px;")
        self.validation_label.setVisible(False)
        main_layout.addWidget(self.validation_label)

        # --- Connections ---
        self.name_edit.textChanged.connect(self.validate)

    def set_validation_lists(self, existing_names: List[str], other_proposed_names: List[str]):
        """Receives lists of names to validate against."""
        self.existing_names_lower = [name.lower() for name in existing_names]
        self.other_proposed_names_lower = [name.lower() for name in other_proposed_names]
        self.validate()

    def set_existing_names(self, names: list[str]):
        """Receives the list of existing names from the parent dialog."""
        self.existing_names_lower = [name.lower() for name in names]
        self.validate() # Re-validate with the new list

    def validate(self):
        """Validates the input name and provides specific error feedback."""
        name = self.name_edit.text().strip()
        name_lower = name.lower()
        error_message = ""

        if not name:
            error_message = _i18n.tr("common.name_cannot_be_empty")
        elif self.ILLEGAL_CHAR_PATTERN.search(name):
            error_message = _i18n.tr("common.illegal_chars")
        elif name_lower in self.existing_names_lower:
            error_message = _i18n.tr("creation_task.exists_in_dest")
        elif name_lower in self.other_proposed_names_lower:
            error_message = _i18n.tr("creation_task.dup_in_list")

        is_currently_valid = not bool(error_message)
        self.validation_label.setText(error_message)
        self.validation_label.setVisible(not is_currently_valid)
        self.name_edit.setProperty('state', 'error' if not is_currently_valid else '')
        self.name_edit.setStyle(QApplication.style())

        if self._is_valid != is_currently_valid:
            self._is_valid = is_currently_valid
            self.validation_changed.emit()

    def is_valid(self) -> bool:
        return self._is_valid

    def get_current_name(self) -> str:
        return self.name_edit.text().strip()

    def get_task_data(self) -> dict:
        self.task_data['output_name'] = self.get_current_name()
        return self.task_data
