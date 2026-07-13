# App/views/dialogs/edit game dialog.py

from pathlib import Path
from typing import Dict, List
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QDialog, QHBoxLayout
from PyQt6.QtCore import Qt
from qfluentwidgets import LineEdit, ComboBox, PrimaryPushButton, PushButton, BodyLabel

from app.core import i18n as _i18n

class EditGameDialog(QDialog):
    """
    A dialog to edit the details of a registered game. It supports two modes:
    a full edit mode and a 'force_selection_mode' for setting only the game_type.
    """

    def __init__(self, game_data: Dict, available_game_types: List[str], parent: QWidget | None = None, force_selection_mode: bool = False):
        super().__init__(parent)
        self.game_data = game_data

        # ---1. Make the main layout ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # ---2. Make all widgets ---
        self.info_label = BodyLabel(
            _i18n.tr("edit_game.must_select_type"), self
        )
        self.name_edit = LineEdit(self)
        self.name_edit.setText(game_data.get("name", ""))
        self.path_edit = LineEdit(self)
        self.path_edit.setText(str(game_data.get("path", "")))
        self.path_edit.setReadOnly(True)

        self.game_type_combo = ComboBox(self)
        # Correction: Fill directly with the type available, without "not set"
        if available_game_types:
            self.game_type_combo.addItems(available_game_types)

            current_type = game_data.get("game_type")
            if current_type and current_type in available_game_types:
                self.game_type_combo.setCurrentText(current_type)
            else:
                # If the current game type is not in the available types, set to the first available type
                self.game_type_combo.setCurrentIndex(0)
        else:
            # if no game types are available, set a placeholder
            self.game_type_combo.setPlaceholderText(_i18n.tr("edit_game.no_types"))
            self.game_type_combo.setEnabled(False)

        # ---3. Create a secondary layout ---

        self.form_layout = QFormLayout()
        self.form_layout.addRow(_i18n.tr("common.name"), self.name_edit)
        self.form_layout.addRow(_i18n.tr("common.path"), self.path_edit)
        self.form_layout.addRow(_i18n.tr("edit_game.mods_type"), self.game_type_combo)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        self.ok_button = PrimaryPushButton(_i18n.tr("common.save"))
        self.cancel_button = PushButton(_i18n.tr("common.cancel"))
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.ok_button)

        # ---4. Add elements to the main layout ---

        main_layout.addWidget(self.info_label)
        main_layout.addLayout(self.form_layout)
        main_layout.addLayout(button_layout)

        # ---5. Apply Handling Mode ---

        if force_selection_mode:
            self.setWindowTitle(_i18n.tr("edit_game.require_key"))
            # Hide the unnecessary field
            self.name_edit.setEnabled(False)

            self.form_layout.labelForField(self.path_edit).setVisible(False)
            self.path_edit.setVisible(False)

            # Show instruction labels
            self.info_label.setVisible(True)

            # Hide the Cancel button
            self.cancel_button.setVisible(False)
        else:
            self.setWindowTitle(_i18n.tr("edit_game.edit_game"))
            self.info_label.setVisible(False)

        self.setFixedWidth(400)

        # ---6. Connections ---
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)


    def get_data(self) -> Dict:
        """Returns the updated data."""
        game_type = self.game_type_combo.currentText()
        return {
            "id": self.game_data["id"],
            "name": self.name_edit.text(),
            "path": Path(self.path_edit.text()),
            "game_type": game_type if game_type != "Not Set" else None
        }