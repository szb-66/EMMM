# app/views/sections/preview_panel.py
from pathlib import Path
from typing import List
from PyQt6.QtCore import QEvent, QSignalBlocker, Qt, pyqtSignal
from collections import defaultdict
from app.services.Iniparsing_service import KeyBinding
from app.views.components.common.ini_file_group_widget import IniFileGroupWidget
from app.views.components.common.keybinding_widget import KeyBindingWidget
from PyQt6.QtWidgets import (
    QFrame,
    QScrollArea,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSizePolicy,
    QStackedWidget,
)

from qfluentwidgets import (
    CaptionLabel,
    SingleDirectionScrollArea,
    LineEdit,
    StrongBodyLabel,
    SubtitleLabel,
    BodyLabel,
    TextEdit,
    SwitchButton,
    PrimaryPushButton,
    PushButton,
    FluentIcon,
    VBoxLayout,
    GroupHeaderCardWidget,
    ExpandGroupSettingCard,
)

# Import ViewModels and Services for type hinting and dependency injection
from app.viewmodels.preview_panel_vm import PreviewPanelViewModel
from app.services.thumbnail_service import ThumbnailService

# Import custom widgets we've designed
from app.views.components.thumbnail_widget import ThumbnailSliderWidget

# from app.views.components.keybinding_widget import KeyBindingWidget # To be created later
PANEL_MARGIN = (12, 12, 12, 12)  # uniform inner padding
DESCRIPTION_MIN_HEIGHT = 60
DESCRIPTION_MAX_HEIGHT = 320


class DescriptionResizeHandle(QFrame):
    height_changed = pyqtSignal(int)
    height_committed = pyqtSignal(int)

    def __init__(self, target: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self.target = target
        self._drag_start_y = 0
        self._drag_start_height = 0

        self.setFixedHeight(8)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_y = int(event.globalPosition().y())
            self._drag_start_height = self.target.height()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            delta = int(event.globalPosition().y()) - self._drag_start_y
            height = max(
                DESCRIPTION_MIN_HEIGHT,
                min(DESCRIPTION_MAX_HEIGHT, self._drag_start_height + delta),
            )
            self.height_changed.emit(height)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.height_committed.emit(self.target.height())
            event.accept()
            return

        super().mouseReleaseEvent(event)


class PreviewPanel(QWidget):
    """The UI panel on the right that displays details for a selected FolderItem."""

    def __init__(
        self,
        viewmodel: PreviewPanelViewModel,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.view_model = viewmodel
        self._displayed_item_id: str | None = None

        self._ini_group_widgets = []
        self._init_ui()
        self._bind_view_models()

    def _init_ui(self):
        self.setStyleSheet(
            "QLineEdit,QTextEdit,QComboBox,QSpinBox,QPushButton{min-width:0;}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(0)

        # Stack: empty view / scrolling view
        self.stack = QStackedWidget(self)
        root.addWidget(self.stack)

        # ── scrolling area (vertical-only) ───────────────────────────────────────
        self.scroll_area = SingleDirectionScrollArea(
            orient=Qt.Orientation.Vertical
        )  # ← fluent class
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        # main content widget
        view = QWidget()
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        vbox = QVBoxLayout(view)
        vbox.setContentsMargins(*PANEL_MARGIN)
        vbox.setSpacing(16)

        # ── header ───────────────────────────────────────────────────────────────
        header = QVBoxLayout()
        header.setSpacing(4)
        self.title_label = SubtitleLabel("No Mod Selected")
        self.title_label.setWordWrap(True)
        self.status_switch = SwitchButton()
        self.status_switch.setOnText("Enabled")
        self.status_switch.setOffText("Disabled")
        header.addWidget(self.title_label)
        header.addWidget(self.status_switch)
        vbox.addLayout(header)

        # ── thumbnail ────────────────────────────────────────────────────────────
        vbox.addWidget(StrongBodyLabel("Preview Images"))
        self.thumbnail_slider = ThumbnailSliderWidget(self.view_model)
        self.thumbnail_slider.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        vbox.addWidget(self.thumbnail_slider)

        # ── description ─────────────────────────────────────────────────────────
        vbox.addWidget(StrongBodyLabel("Description"))
        self.description_editor = TextEdit()
        self.description_editor.setPlaceholderText("No description available.")
        self.description_editor.setMinimumHeight(DESCRIPTION_MIN_HEIGHT)
        self.description_editor.setMaximumHeight(DESCRIPTION_MAX_HEIGHT)
        self.description_editor.setFixedHeight(
            self.view_model.get_description_editor_height()
        )
        self.description_editor.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.description_editor.installEventFilter(self)
        vbox.addWidget(self.description_editor)
        self.description_resize_handle = DescriptionResizeHandle(
            self.description_editor, self
        )
        self.description_resize_handle.height_changed.connect(
            self._set_description_editor_height
        )
        self.description_resize_handle.height_committed.connect(
            self.view_model.save_description_editor_height
        )
        vbox.addWidget(self.description_resize_handle)
        self.save_description_button = PushButton(FluentIcon.SAVE, "Save Description")
        self.save_description_button.hide()
        vbox.addWidget(self.save_description_button, 0, Qt.AlignmentFlag.AlignLeft)

        # ── config ───────────────────────────────────────────────────────────────
        vbox.addWidget(StrongBodyLabel("Mod Configuration"))
        cfg_wrap = QWidget()
        cfg_wrap.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.ini_config_layout = QVBoxLayout(cfg_wrap)
        self.ini_config_layout.setContentsMargins(0, 0, 0, 0)
        self.ini_config_layout.setSpacing(4)
        vbox.addWidget(cfg_wrap)

        self.save_config_button = PrimaryPushButton(
            FluentIcon.SAVE, "Save Configuration"
        )
        self.save_config_button.hide()
        vbox.addWidget(self.save_config_button, 0, Qt.AlignmentFlag.AlignLeft)

        vbox.addStretch(1)

        # commit scrolling view
        self.scroll_area.setWidget(view)

        # ── stack pages ──────────────────────────────────────────────────────────
        self.empty_view = BodyLabel(
            "Select a mod from the grid to see its details",
        )
        self.empty_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.empty_view)
        self.stack.addWidget(self.scroll_area)
        self.stack.setCurrentWidget(self.empty_view)

    def _bind_view_models(self):
        """Connects this panel's widgets and slots to the ViewModel."""
        # VM -> View
        self.view_model.item_loaded.connect(self._on_item_loaded)
        self.view_model.ini_config_ready.connect(self._on_ini_config_ready)
        self.view_model.is_description_dirty_changed.connect(
            self.save_description_button.setVisible
        )
        self.view_model.ini_dirty_state_changed.connect(
            self.save_config_button.setVisible
        )
        self.view_model.save_description_state.connect(
            self._on_save_description_state_changed
        )
        self.view_model.save_config_state.connect(self._on_save_config_state_changed)

        # View -> VM
        self.description_editor.textChanged.connect(self._on_description_text_changed)
        self.save_description_button.clicked.connect(self.view_model.save_description)
        self.save_config_button.clicked.connect(self.view_model.save_ini_config)
        self.status_switch.checkedChanged.connect(
            self.view_model.toggle_current_item_status
        )

        # The ThumbnailSliderWidget will handle its own internal bindings for add/remove,
        # calling the appropriate methods on the view_model.
        # e.g., self.thumbnail_slider.add_requested.connect(self.view_model.add_new_thumbnail)

    # --- SLOTS (Responding to ViewModel Signals) ---

    def _on_item_loaded(self, item_data: dict | None) -> None:
        """Load item data into the panel, using lightweight update when the same
        item re-emits (e.g. toggle modified only the status/title)."""
        new_id = item_data.get("id") if item_data else None

        # ── lightweight update: same item, only status/title may have changed ──
        if new_id and new_id == self._displayed_item_id:
            full_title = item_data.get("actual_name", "N/A")
            self.title_label.setText(full_title)
            with QSignalBlocker(self.status_switch):
                self.status_switch.setChecked(item_data.get("is_enabled", False))
            return

        # ── full clear ─────────────────────────────────────────────────────────
        self.clear_panel()

        if not item_data:
            self._displayed_item_id = None
            return

        # ── show main content ────────────────────────────────────────────────────
        self.stack.setCurrentWidget(self.scroll_area)

        # ── reset transient state ───────────────────────────────────────────────
        self._clear_ini_layout()
        self.save_description_button.hide()
        self.save_config_button.hide()

        # ── title ───────────────────────────────────────────────────────────────
        full_title = item_data.get("actual_name", "N/A")
        self.title_label.setText(full_title)

        # ── enable/disable switch (block signal to avoid feedback loop) ─────────
        with QSignalBlocker(self.status_switch):
            self.status_switch.setChecked(item_data.get("is_enabled", False))

        # ── thumbnails ──────────────────────────────────────────────────────────
        self.thumbnail_slider.set_image_paths(item_data.get("preview_images", []))

        # ── description ─────────────────────────────────────────────────────────
        desc = item_data.get("description", "")
        self.description_editor.setText(desc)
        self.save_description_button.hide()

        # ── track displayed item ────────────────────────────────────────────────
        self._displayed_item_id = new_id

    def _on_ini_config_ready(self, keybindings: list[KeyBinding]) -> None:
        """Populate ini-config panel dengan group per‐file, no overlap."""
        self._clear_ini_layout()
        self._ini_group_widgets.clear()

        # ── empty state
        if not keybindings:
            lbl = CaptionLabel("No editable keybindings found in this mod.")
            lbl.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            self.ini_config_layout.addWidget(lbl)
            self._ini_group_widgets.append(lbl)
            self.ini_config_layout.addStretch(1)
            return

        # ── grouping & sorting
        by_file: dict[Path, list[KeyBinding]] = defaultdict(list)
        for kb in keybindings:
            by_file[kb.source_file].append(kb)

        root_path: Path | None = getattr(
            self.view_model.current_item_model, "folder_path", None
        )

        files_sorted = sorted(
            by_file, key=lambda p: (root_path and p.parent != root_path, str(p).lower())
        )

        # ── build UI
        for ini_path in files_sorted:
            # label relative ke root jika possible
            label = (
                str(ini_path.relative_to(root_path))
                if root_path and root_path in ini_path.parents
                else ini_path.name
            )

            group = IniFileGroupWidget(label, ini_path, self)
            group.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            group.open_file_requested.connect(self.view_model.open_ini_file)

            for kb in by_file[ini_path]:
                widget = KeyBindingWidget(kb, parent=group)
                widget.value_changed.connect(self.view_model.on_keybinding_edited)
                group.add_binding_widget(widget)

            self.ini_config_layout.addWidget(group)
            self._ini_group_widgets.append(group)
            self.ini_config_layout.addSpacing(12)  # simple visual gap

        self.ini_config_layout.addStretch(1)
        self.ini_config_layout.activate()

    def _clear_ini_layout(self):
        """Helper to remove all old keybinding widgets and cards."""
        while self.ini_config_layout.count():
            item = self.ini_config_layout.takeAt(0)
            if item is None:
                continue

            # widget langsung
            if w := item.widget():
                w.deleteLater()
                continue

            # sub-layout rekursif
            if lay := item.layout():
                while lay.count():
                    sub_item = lay.takeAt(0)
                    widget = sub_item.widget() if sub_item else None
                    if widget is not None:
                        widget.deleteLater()
                continue

            # spacerItem – cukup di-drop (GC yang urus)
            # item.spacerItem() is not None untuk spacer; nothing else needed

        self._ini_group_widgets.clear()
        self.ini_config_layout.update()

    def _on_description_text_changed(self):
        """Memberitahu ViewModel setiap kali teks di editor berubah."""
        self.view_model.on_description_changed(self.description_editor.toPlainText())

    def _set_description_editor_height(self, height: int):
        height = max(DESCRIPTION_MIN_HEIGHT, min(DESCRIPTION_MAX_HEIGHT, height))
        self.description_editor.setFixedHeight(height)

    def eventFilter(self, obj, event):
        if (
            obj is self.description_editor
            and event.type() == QEvent.Type.FocusOut
            and self.view_model.is_description_dirty
        ):
            self.view_model.save_description()

        return super().eventFilter(obj, event)

    # ADD THIS SLOT
    def _on_save_description_state_changed(self, text: str, is_enabled: bool):
        """Mengubah teks dan status tombol simpan."""
        self.save_description_button.setText(text)
        self.save_description_button.setEnabled(is_enabled)

    # ADD THIS NEW SLOT
    def _on_save_config_state_changed(self, text: str, is_enabled: bool):
        """Mengubah teks dan status tombol simpan konfigurasi."""
        self.save_config_button.setText(text)
        self.save_config_button.setEnabled(is_enabled)

    def clear_panel(self):
        """Clears all displayed data from the panel."""
        self._displayed_item_id = None
        self.stack.setCurrentWidget(self.empty_view)
        if self.thumbnail_slider:
            self.thumbnail_slider.set_image_paths([])
