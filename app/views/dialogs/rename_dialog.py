# app/views/dialogs/rename_dialog.py

import re
from typing import List
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout
from qfluentwidgets import LineEdit, PrimaryPushButton, PushButton, BodyLabel

from app.core import i18n as _i18n

class RenameDialog(QDialog):
    """
    A dialog for renaming an item. It provides real-time validation to ensure
    the new name is valid and different from the original.
    """
    ILLEGAL_CHAR_PATTERN = re.compile(r'[\\/:*?"<>|]')

    def __init__(self, current_name: str, existing_names: List[str], parent=None):
        super().__init__(parent)
        self.original_name_lower = current_name.lower()
        self.other_existing_names = [name.lower() for name in existing_names if name.lower() != self.original_name_lower]

        # --- NEW: Flag to track user interaction ---
        self.user_has_interacted = False
        # ----------------------------------------

        self.setWindowTitle(_i18n.tr("rename.title"))
        self.setFixedWidth(350)

        # --- Widgets ---
        self.name_edit = LineEdit(self)
        self.name_edit.setText(current_name)
        self.name_edit.selectAll()

        self.validation_label = BodyLabel("", self)
        self.validation_label.setStyleSheet("color: #f97171;")
        self.validation_label.setVisible(False)

        # --- Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.name_edit)
        main_layout.addWidget(self.validation_label)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        self.ok_button = PrimaryPushButton(_i18n.tr("common.rename"))
        cancel_button = PushButton(_i18n.tr("common.cancel"))
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(self.ok_button)
        main_layout.addLayout(button_layout)

        # --- Connections ---
        self.name_edit.textChanged.connect(self._validate_input)
        self.ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        self.ok_button.setDefault(True)

        self.name_edit.returnPressed.connect(self.ok_button.animateClick)

        # --- Initial State ---
        self.ok_button.setEnabled(False)


    def _validate_input(self):
        """[REVISED] Validates the new name in real-time, with improved UX."""
        # The first time the user types, set the interaction flag to True.
        if not self.user_has_interacted:
            self.user_has_interacted = True

        new_name = self.name_edit.text().strip()
        new_name_lower = new_name.lower()
        error_message = ""

        if not new_name:
            error_message = _i18n.tr("common.name_cannot_be_empty")
        # Only show "not changed" error if the user has actually typed something.
        elif new_name_lower == self.original_name_lower and self.user_has_interacted:
            error_message = _i18n.tr("common.name_not_changed")
        elif self.ILLEGAL_CHAR_PATTERN.search(new_name):
            error_message = _i18n.tr("common.illegal_chars")
        elif new_name_lower in self.other_existing_names:
            error_message = _i18n.tr("common.duplicate_name", name=new_name)

        self.validation_label.setText(error_message)
        self.validation_label.setVisible(bool(error_message))

        # The button is enabled only if the text is not the original AND there is no error message.
        is_changed = new_name_lower != self.original_name_lower
        self.ok_button.setEnabled(is_changed and not bool(error_message))

    def get_new_name(self) -> str:
        """Returns the validated new name."""
        return self.name_edit.text().strip()
