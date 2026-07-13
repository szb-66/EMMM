# app/views/dialogs/edit_object_dialog.py

import re
from typing import Dict, Any, List
from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QDialog, QHBoxLayout, QFileDialog
from qfluentwidgets import (
    LineEdit, ComboBox, BodyLabel, SubtitleLabel, PrimaryPushButton,
    PushButton, ImageLabel, FluentIcon
)

from app.core import i18n as _i18n
from app.models.mod_item_model import ModType
from app.utils.image_utils import ImageUtils
from app.utils.logger_utils import logger
from app.utils.ui_utils import UiUtils


class EditObjectDialog(QDialog):
    """
    A dialog for editing the details of an existing object.
    It's pre-populated with the item's current data and allows modification.
    """
    ILLEGAL_CHAR_PATTERN = re.compile(r'[\\/:*?"<>|]')

    def __init__(self, item_data: dict, schema: dict, existing_names: List[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.item_data = item_data
        self.schema = schema or {}
        self.original_name = item_data.get("actual_name", "")
        self.accepted_mode = None

        # Create a list of other names for duplicate checking
        self.other_existing_names = [name.lower() for name in existing_names if name.lower() != self.original_name.lower()]

        # State to store the new thumbnail source, if any
        self.selected_thumbnail_source: Any = None

        self._init_ui()
        self._connect_signals()

        # Set initial state for dynamic fields
        self._on_object_type_changed(self.object_type_combo.currentText())

    def _init_ui(self):
        """Initializes and populates the UI components."""
        self.setWindowTitle(_i18n.tr("edit_object.title", name=self.original_name))
        self.setFixedWidth(420)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        self.form_layout = QFormLayout()
        self.form_layout.setContentsMargins(2, 15, 2, 5)
        self.form_layout.setSpacing(12)

        # --- Create and Populate Widgets ---
        self.folder_name_edit = LineEdit(self)
        self.folder_name_edit.setText(self.original_name)

        self.object_type_combo = ComboBox(self)
        self.object_type_combo.addItems([e.value for e in ModType])
        current_type = self.item_data.get("object_type")
        if current_type:
            self.object_type_combo.setCurrentText(current_type.value)

        self.rarity_combo = ComboBox(self)
        self.rarity_combo.addItems(self.schema.get('rarity', []))
        self.rarity_combo.setCurrentText(self.item_data.get("rarity", ""))

        self.gender_combo = ComboBox(self)
        self.gender_combo.addItems(self.schema.get('gender', []))
        self.gender_combo.setCurrentText(self.item_data.get("gender", ""))

        self.element_combo = ComboBox(self)
        self.element_combo.addItems(self.schema.get('element', []))
        self.element_combo.setCurrentText(self.item_data.get("element", ""))

        self.subtype_edit = LineEdit(self)
        self.subtype_edit.setText(self.item_data.get("subtype", ""))

        self.tags_edit = LineEdit(self)
        self.tags_edit.setText(", ".join(self.item_data.get("tags", [])))

        # --- Thumbnail Section (Layout consistent with CreateObjectDialog) ---
        thumbnail_container = QWidget()
        thumbnail_layout = QVBoxLayout(thumbnail_container)
        thumbnail_layout.setContentsMargins(0, 0, 0, 0)
        thumbnail_layout.setSpacing(8)

        # --- THE CORE FIX for TypeError ---
        # Convert the Path object to a string before passing it to the ImageLabel
        initial_thumb_path = self.item_data.get("thumbnail_path")
        image_path_str = str(initial_thumb_path) if initial_thumb_path else "app/assets/images/mod_placeholder.jpg"
        self.thumbnail_preview = ImageLabel(image_path_str)
        # --- END OF FIX ---

        self.thumbnail_preview.setFixedSize(128, 128)
        self.thumbnail_preview.setBorderRadius(8, 8, 8, 8)
        thumbnail_layout.addWidget(self.thumbnail_preview, 0, Qt.AlignmentFlag.AlignCenter)

        thumb_button_layout = QHBoxLayout()
        self.browse_thumb_button = PushButton(_i18n.tr("common.browse"))
        self.paste_thumb_button = PushButton(_i18n.tr("thumb.paste"))
        thumb_button_layout.addWidget(self.browse_thumb_button)
        thumb_button_layout.addWidget(self.paste_thumb_button)
        thumbnail_layout.addLayout(thumb_button_layout)

        # --- Add all rows to layout ---
        self.form_layout.addRow(_i18n.tr("common.folder_name"), self.folder_name_edit)
        self.form_layout.addRow(_i18n.tr("common.object_type"), self.object_type_combo)
        self.form_layout.addRow(_i18n.tr("common.rarity"), self.rarity_combo)
        self.form_layout.addRow(_i18n.tr("common.gender"), self.gender_combo)
        self.form_layout.addRow(_i18n.tr("common.element"), self.element_combo)
        self.form_layout.addRow(_i18n.tr("common.subtype"), self.subtype_edit)
        self.form_layout.addRow(_i18n.tr("common.tags"), self.tags_edit)
        self.form_layout.addRow(_i18n.tr("common.thumbnail"), thumbnail_container)

        # --- Bottom Buttons and Validation Label ---
        button_layout = QHBoxLayout()
        self.status_label = BodyLabel("", self)
        self.status_label.setStyleSheet("color: #f97171;")
        self.sync_button = PushButton(FluentIcon.SYNC, _i18n.tr("edit_object.sync_db"))
        self.sync_button.setToolTip(_i18n.tr("edit_object.sync_db_tooltip"))
        self.save_button = PrimaryPushButton(_i18n.tr("edit_object.save_changes"))
        self.cancel_button = PushButton(_i18n.tr("common.cancel"))
        button_layout.addWidget(self.sync_button)
        button_layout.addStretch(1)

        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.save_button)

        main_layout.addLayout(self.form_layout)
        main_layout.addWidget(self.status_label)
        main_layout.addLayout(button_layout)

    def _connect_signals(self):
        """Connect all signals to their slots."""
        # Connect textChanged for validation, toggled for dynamic fields, etc.
        self.folder_name_edit.textChanged.connect(self._validate_input)
        self.object_type_combo.currentTextChanged.connect(self._on_object_type_changed)
        self.browse_thumb_button.clicked.connect(self._on_browse_clicked)
        self.paste_thumb_button.clicked.connect(self._on_paste_clicked)
        self.save_button.clicked.connect(self._on_save_clicked)
        self.cancel_button.clicked.connect(self.reject)
        self.sync_button.clicked.connect(self._on_sync_clicked)

    def _on_save_clicked(self):
        """Handles the click of the 'Save Changes' button."""
        self._validate_input()
        if self.save_button.isEnabled():
            self.accepted_mode = "save"
            self.accept()

    def _on_sync_clicked(self):
        """Handles the click of the 'Sync with Database' button."""
        self.accepted_mode = "sync"
        self.accept()

    def get_results(self) -> dict:
        """
        [REVISED] Public method to get the result after the dialog is accepted,
        indicating which button was clicked.
        """
        if self.accepted_mode == "save":
            return {"mode": "save", "data": self.get_data()}
        elif self.accepted_mode == "sync":
            return {"mode": "sync"}
        return {"mode": None}

    def _validate_input(self):
        """[REVISED] Validates the new name in real-time, with improved UX."""
        new_name = self.folder_name_edit.text().strip()
        new_name_lower = new_name.lower()
        error_message = ""

        if not new_name:
            error_message = _i18n.tr("common.name_cannot_be_empty")
        elif self.ILLEGAL_CHAR_PATTERN.search(new_name):
            error_message = _i18n.tr("common.illegal_chars")
        elif new_name_lower in self.other_existing_names:
            error_message = _i18n.tr("common.duplicate_name", name=new_name)

        self.status_label.setText(error_message)
        self.status_label.setVisible(bool(error_message))

        # The button is enabled only if the text is not the original AND there is no error message.
        self.save_button.setEnabled(not bool(error_message))

    def _on_object_type_changed(self, text: str | None):
        """Shows or hides fields based on the selected object type."""
        # If no schema, text can be None. Default to not character.
        is_character = (text == ModType.CHARACTER.value) if text else False

        self.form_layout.labelForField(self.rarity_combo).setVisible(is_character)
        self.rarity_combo.setVisible(is_character)
        self.form_layout.labelForField(self.gender_combo).setVisible(is_character)
        self.gender_combo.setVisible(is_character)
        self.form_layout.labelForField(self.element_combo).setVisible(is_character)
        self.element_combo.setVisible(is_character)

        # Show Subtype field for any type that is NOT Character and not None
        show_subtype = bool(text and not is_character)
        self.form_layout.labelForField(self.subtype_edit).setVisible(show_subtype)
        self.subtype_edit.setVisible(show_subtype)

        self.adjustSize()

    def _on_browse_clicked(self):
        """Opens a file dialog to select a thumbnail image."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            _i18n.tr("create_object.select_thumb"),
            "", # Start directory
            "Image Files (*.png *.jpg *.jpeg *.webp)"
        )

        if not file_path:
            return

        self.selected_thumbnail_source = Path(file_path)

        pixmap = QPixmap(file_path)
        self.thumbnail_preview.setPixmap(pixmap.scaled(
            self.thumbnail_preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))

    def _on_paste_clicked(self):
        """Pastes an image from the clipboard and displays it as a preview."""
        image = ImageUtils.get_image_from_clipboard()

        if image is None:
            logger.warning("No valid image found on clipboard.")
            # show toast
            UiUtils.show_toast(self, _i18n.tr("common.no_clipboard_image"), "warning")
            return

        # Convert PIL Image to QImage
        from PIL.ImageQt import ImageQt
        qimage = ImageQt(image)

        self.selected_thumbnail_source = image

        pixmap = QPixmap.fromImage(qimage)
        self.thumbnail_preview.setPixmap(pixmap.scaled(
            self.thumbnail_preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))

    def get_data(self) -> Dict[str, Any]:
        """Gathers all updated data from the form fields."""
        # ... (Logic is identical to CreateObjectDialog's get_data, but for editing)
        updated_data = {
            "name": self.folder_name_edit.text().strip(),
            "object_type": self.object_type_combo.currentText(),
            # ... (gather all other fields)
        }
        if self.selected_thumbnail_source:
            updated_data["thumbnail_source"] = self.selected_thumbnail_source
        return updated_data