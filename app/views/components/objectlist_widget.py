# App/views/components/objectlist widget.py

from PyQt6.QtCore import pyqtSignal, QSize, Qt, QMimeData, QByteArray
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QSizePolicy, QWidget, QHBoxLayout
from qfluentwidgets import (
    StrongBodyLabel,
    CaptionLabel,
    FluentIcon,
    IconWidget,
    IndeterminateProgressRing,
    VBoxLayout,
    AvatarWidget,
    RoundMenu,
)

# Import models and services for type hinting
from app.models.mod_item_model import ModType
from app.utils.ui_utils import UiUtils
from app.viewmodels.mod_list_vm import ModListViewModel
from app.utils.logger_utils import logger
from app.views.dialogs.edit_object_dialog import EditObjectDialog
from app.core.constants import EMMM_MOD_MIME_TYPE

class ObjectListItemWidget(QWidget):
    """
    A self-contained widget to display a single ObjectItem. It forwards all
    user interactions to the ViewModel and updates its display based on the item model.
    """

    # Custom signal to notify the parent panel of a selection click.

    item_selected = pyqtSignal(object)  # Emits the item model

    def __init__(
        self,
        item_data: dict,
        viewmodel: ModListViewModel,
        display_mode: str = "list",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.item_data = item_data
        self.view_model = viewmodel
        self.display_mode = display_mode

        self._init_ui()
        self._connect_signals()
        self.set_data(self.item_data)
        self.setAcceptDrops(True)

    def _init_ui(self):
        """Initializes the UI components of the widget with Fluent components."""
        self.setObjectName("ObjectListItem")
        if self.display_mode == "card":
            main_layout = VBoxLayout(self)
            main_layout.setContentsMargins(6, 8, 6, 8)
            main_layout.setSpacing(6)
            main_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            self.setMinimumHeight(136)
        else:
            main_layout = QHBoxLayout(self)
            main_layout.setContentsMargins(8, 8, 8, 8)
            main_layout.setSpacing(10)

        # ---1. Thumbnail as Avatar ---

        self.avatar = AvatarWidget(self)
        self.avatar.setRadius(34)
        self.avatar.setFixedSize(QSize(76, 76))

        # Added Processing Ring as Overlay in Avatar

        self.processing_ring = IndeterminateProgressRing(self.avatar)
        self.processing_ring.setFixedSize(32, 32)
        ring_x = (self.avatar.width() - self.processing_ring.width()) // 2
        ring_y = (self.avatar.height() - self.processing_ring.height()) // 2
        self.processing_ring.move(ring_x, ring_y)
        self.processing_ring.hide()

        if self.display_mode == "card":
            main_layout.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignHCenter)
        else:
            main_layout.addWidget(self.avatar)

        # ---2. Info Block (Name + Passive Label Status) ---

        info_widget = QWidget(self)
        info_layout = VBoxLayout(info_widget)
        info_layout.setContentsMargins(0 if self.display_mode == "card" else 4, 0, 0, 0)
        info_layout.setSpacing(2)
        info_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | (
                Qt.AlignmentFlag.AlignHCenter
                if self.display_mode == "card"
                else Qt.AlignmentFlag.AlignLeft
            )
        )

        self.name_label = StrongBodyLabel()
        self.name_label.setObjectName("NameLabel")
        self.name_label.setWordWrap(True)
        self.name_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
            if self.display_mode == "card"
            else Qt.AlignmentFlag.AlignLeft
        )
        self.name_label.setMaximumHeight(44 if self.display_mode == "card" else 42)
        info_layout.addWidget(self.name_label)

        self.status_text = CaptionLabel()
        self.status_text.setObjectName("StatusTextLabel")
        info_layout.addWidget(self.status_text)
        main_layout.addWidget(info_widget)

        if self.display_mode == "list":
            # ---3. Spacer to push the icon pin to the right ---
            spacer = QWidget(self)
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            main_layout.addWidget(spacer)

        # ---4. Pin Icon ---

        self.pin_icon = IconWidget(FluentIcon.PIN, self)
        self.pin_icon.setFixedSize(16, 16)
        self.pin_icon.setToolTip("Pinned")
        self.pin_icon.hide()
        if self.display_mode == "card":
            self.pin_icon.move(self.width() - 22, 6)
            self.pin_icon.raise_()
        else:
            main_layout.addWidget(self.pin_icon)

    def _connect_signals(self):
        """Connects internal UI widget signals to their handler methods."""
        pass

    def set_data(self, item_data: dict):
        """Updates the widget's display with new data from a dictionary."""
        self.item_data = item_data
        actual_name = self.item_data.get("actual_name", "")
        self.name_label.setText(actual_name)

        is_enabled = self.item_data.get("is_enabled")
        self.status_text.setText("Enabled" if is_enabled else "Disabled")
        self.status_text.setVisible(self.display_mode == "list")
        self.pin_icon.setVisible(self.item_data.get("is_pinned", False))

        id_data = self.item_data.get("id") or ""
        thumbnail_path = self.item_data.get("thumbnail_path")

        if not thumbnail_path or not id_data:
            # get initial from actual_name

            self.avatar.setText(self.view_model.get_initial_name(actual_name))
            return None

        thumbnail_pixmap = self.view_model.get_thumbnail(
            item_id=id_data,
            source_path=thumbnail_path,
            default_type="object",
        )
        self.avatar.setPixmap(thumbnail_pixmap)
        self.avatar.setRadius(34)
        self.avatar.setFixedSize(QSize(76, 76))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.display_mode == "card":
            self.pin_icon.move(max(4, self.width() - 22), 6)

    def show_processing_state(self, is_processing: bool, text: str = "Processing..."):
        """Flow 3.1a, 4.2: Shows a visual indicator that the item is being processed."""
        self.setEnabled(not is_processing)
        if is_processing:
            self.processing_ring.show()
        else:
            self.processing_ring.hide()

    # ---Qt Event Handlers ---

    def contextMenuEvent(self, event):
        """Creates and shows a context menu on right-click."""
        menu = RoundMenu(parent=self)
        item_id = self.item_data.get("id")

        # ---Enable/dynamic disable/disable action ---
        is_enabled = self.item_data.get("is_enabled", False)
        action_text = "Disable" if is_enabled else "Enable"
        action_icon = FluentIcon.REMOVE_FROM if is_enabled else FluentIcon.ACCEPT

        toggle_action = QAction(action_icon.icon(), action_text, self)
        toggle_action.triggered.connect(
            lambda: self.view_model.toggle_item_status(
                self.item_data.get("id") or "false"
            )
        )
        menu.addAction(toggle_action)

        menu.addSeparator()

        # Open in File Explorer action
        open_folder_action = QAction(
            FluentIcon.FOLDER.icon(), "Open in File Explorer", self
        )
        open_folder_action.triggered.connect(
            lambda: self.view_model.open_in_explorer(self.item_data.get("id") or "")
        )
        menu.addAction(open_folder_action)

        menu.addSeparator()

        pin_action_text = "Unpin" if self.item_data.get("is_pinned") else "Pin"
        pin_action = QAction(FluentIcon.PIN.icon(), pin_action_text, self)
        pin_action.triggered.connect(
            lambda: self.view_model.toggle_pin_status(item_id)
        )

        menu.addAction(pin_action)

        edit_action = QAction(FluentIcon.EDIT.icon(), "Edit...", self)
        edit_action.triggered.connect(self._on_edit_requested)
        menu.addAction(edit_action)

        convert_menu = RoundMenu("Move to", self)
        convert_menu.setIcon(FluentIcon.MOVE)

        current_object_type_str = self.item_data.get("object_type", "Unknown")
        # Loop with all ModType enum values
        for mod_type in ModType:
            action = QAction(mod_type.value, self)

            # Mark or disable the currently active type
            if mod_type.value == current_object_type_str:
                action.setEnabled(False)
                # Add "(current)" for clarity
                action.setText(f"{mod_type.value} (current)")

            # Connect triggered signal to the method in the ViewModel
            # We use lambda to forward the item_id and new type
            action.triggered.connect(
                lambda checked=False, item_id_arg=item_id, new_type_arg=mod_type:
                self.view_model.convert_object_type(item_id_arg, new_type_arg)
            )
            convert_menu.addAction(action)

        # Tambahkan submenu ke menu utama
        menu.addMenu(convert_menu)

        sync_action = QAction(FluentIcon.SYNC.icon(), "Sync with Database...", self)
        sync_action.triggered.connect(
            lambda: self.view_model.initiate_sync_for_item(item_id)
        )
        menu.addAction(sync_action)
        menu.addSeparator()

        delete_action = QAction(FluentIcon.DELETE.icon(), "Delete", self)
        delete_action.triggered.connect(self._on_delete_requested)
        menu.addAction(delete_action)

        # Show menus in the cursor position

        menu.exec(event.globalPos())

    def mousePressEvent(self, event):
        """Flow 2.3: Notifies the parent panel that this item was clicked."""

        self.item_selected.emit(self.item_data)
        super().mousePressEvent(event)
        pass

    def dragEnterEvent(self, event):
        """Accepts internal mod drags from the foldergrid (cross-character move)."""
        if event.mimeData().hasFormat(EMMM_MOD_MIME_TYPE):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        """Moves a dropped mod into this character's root folder via cross-VM signal."""
        mime = event.mimeData()
        if not mime.hasFormat(EMMM_MOD_MIME_TYPE):
            super().dropEvent(event)
            return

        dropped_id = bytes(mime.data(EMMM_MOD_MIME_TYPE)).decode("utf-8")
        if not dropped_id:
            event.ignore()
            return

        target_path = self.item_data.get("folder_path")
        if target_path:
            self.view_model.move_to_character_requested.emit(dropped_id, target_path)
            event.acceptProposedAction()
        else:
            event.ignore()

    def showEvent(self, event):
        """Triggers lazy-hydration when the widget becomes visible."""
        super().showEvent(event)
        # Revised: Data access from DICT

        if self.item_data.get("is_skeleton", False):
            item_id = self.item_data.get("id") or ""
            self.view_model.request_item_hydration(item_id)

    # ---Private Slots (Handling UI events) ---


    def _on_edit_requested(self):
        """
        [NEW] Handles the 'Edit' context menu action. It fetches the necessary
        data from the ViewModel and shows the EditObjectDialog.
        """
        item_id = self.item_data.get("id")
        if not item_id:
            return

        # 1. Get all data required by the dialog from the ViewModel
        schema = self.view_model.get_current_game_schema()
        # The dialog needs all other names to check for duplicates
        all_names = self.view_model.get_all_item_names()

        # The dialog needs the full data of the item being edited
        item_to_edit_model = next((i for i in self.view_model.master_list if i.id == item_id), None)
        if not item_to_edit_model:
            logger.error(f"Could not find item model for ID {item_id} to edit.")
            return

        # Convert the model to a dictionary that the dialog can use
        item_data_dict = self.view_model._create_dict_from_item(item_to_edit_model)

        # 2. Create and show the dialog
        dialog = EditObjectDialog(
            item_data=item_data_dict,
            schema=schema,
            existing_names=all_names,
            parent=self.window()
        )

        # 3. Process the result if the user saves
        if dialog.exec():
            result = dialog.get_results()

            if result["mode"] == "save":
                # if the user chose to save manually
                updated_data = result["data"]
                self.view_model.update_object_item(item_id, updated_data)
            elif result["mode"] == "sync":
                # if the user chose to sync with the database
                self.view_model.initiate_sync_for_item(item_id)

    def _on_delete_requested(self):
        """
        [NEW] Shows a confirmation dialog before proceeding with the deletion
        for an objectlist item.
        """
        item_id = self.item_data.get("id")
        item_name = self.item_data.get("actual_name")
        if not item_id or not item_name:
            return

        title = "Confirm Deletion"
        content = (f"Are you sure you want to move the object '{item_name}' and all its mods to the Recycle Bin?\n\n"
                   "This action cannot be undone directly from the app.")

        if UiUtils.show_confirm_dialog(self.window(), title, content, "Yes, Delete", "Cancel"):
            # If the user confirms, call the ViewModel method
            self.view_model.delete_item(item_id)
