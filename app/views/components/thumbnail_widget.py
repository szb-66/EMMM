# app/views/components/thumbnail_widget.py

from collections import OrderedDict
from pathlib import Path
from typing import List

from PyQt6.QtCore import Qt, QSize, QTimer, QEvent, QSettings, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QContextMenuEvent,
    QDragEnterEvent,
    QDropEvent,
    QPixmap,
    QResizeEvent,
)
from PyQt6.QtWidgets import (
    QFileDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QSizePolicy,
    QScrollArea,
    QLabel,
    QFrame,
    QDialog,
)

from qfluentwidgets import (
    InfoBar,
    InfoBarPosition,
    MessageBox,
    RoundMenu,
    ToolButton,
    FluentIcon,
    CaptionLabel,
    ProgressRing,
    SubtitleLabel,
    TransparentPushButton,
    VBoxLayout,
)

from app.viewmodels.preview_panel_vm import PreviewPanelViewModel
from app.core.constants import SUPPORTED_IMAGE_EXTENSIONS

THUMB_HEIGHT = 210
THUMB_SPACING = 8
THUMB_WIDTH_MIN = 80
THUMB_WIDTH_MAX = 400


class FullSizeImageDialog(QDialog):
    """Non-modal dialog that displays an image with contain-fit scaling."""

    def __init__(self, pixmap: QPixmap, title: str = "", parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle(f"Preview - {title}" if title else "Preview")
        self.setMinimumSize(400, 300)

        self._original_pixmap = pixmap

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setContextMenuPolicy(
            Qt.ContextMenuPolicy.PreventContextMenu
        )
        self.image_label.installEventFilter(self)
        layout.addWidget(self.image_label)

        # Restore saved geometry or use default size
        self._restore_geometry()

        # Apply initial contain-fit scaling
        self._update_image()

    def _update_image(self):
        """Scale the pixmap to fit the label, maintaining aspect ratio (contain)."""
        if self._original_pixmap.isNull():
            return
        label_size = self.image_label.size()
        if label_size.width() <= 0 or label_size.height() <= 0:
            return
        scaled = self._original_pixmap.scaled(
            label_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_image()

    def eventFilter(self, obj, event):
        if obj is self.image_label and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.RightButton:
                self.close()
                return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.close()
        super().mousePressEvent(event)

    def closeEvent(self, event):
        self._save_geometry()
        super().closeEvent(event)

    def _save_geometry(self):
        settings = QSettings("EMMM", "FullSizeImageDialog")
        settings.setValue("geometry", self.saveGeometry())

    def _restore_geometry(self):
        settings = QSettings("EMMM", "FullSizeImageDialog")
        geometry = settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            img_size = self._original_pixmap.size()
            max_w = 1200
            max_h = 900
            dlg_w = min(img_size.width() + 40, max_w)
            dlg_h = min(img_size.height() + 40, max_h)
            self.resize(int(dlg_w), int(dlg_h))


class ThumbnailGalleryLabel(QLabel):
    """A clickable thumbnail label with selection highlight."""

    clicked = pyqtSignal(int)
    doubleClicked = pyqtSignal(int)

    def __init__(self, image_path: Path, index: int, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.index = index
        self._pixmap = None
        self._is_selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_style()

    def set_pixmap(self, pixmap):
        self._pixmap = pixmap
        super().setPixmap(pixmap)

    def set_selected(self, selected: bool):
        if self._is_selected == selected:
            return
        self._is_selected = selected
        self._update_style()

    def _update_style(self):
        if self._is_selected:
            self.setStyleSheet(
                "border: 2px solid #60cdff; border-radius: 4px; background-color: rgba(96, 205, 255, 0.08);"
            )
        else:
            self.setStyleSheet(
                "border: 2px solid transparent; border-radius: 4px;"
            )

    def mousePressEvent(self, ev):
        self.clicked.emit(self.index)
        super().mousePressEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        self.doubleClicked.emit(self.index)
        super().mouseDoubleClickEvent(ev)


class ThumbnailSliderWidget(QWidget):
    """
    A widget that displays preview images in a horizontally scrollable gallery,
    along with controls for managing images (add, paste, remove, clear, set as cover).
    """

    def __init__(
        self,
        viewmodel: PreviewPanelViewModel,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.view_model = viewmodel
        self._image_paths: List[Path] = []
        self._selected_index = 0
        self._thumb_labels: List[ThumbnailGalleryLabel] = []
        self._pixmap_cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._pixmap_cache_max = 200

        # Enable drag & drop for image files
        self.setAcceptDrops(True)

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        """Initializes the UI components of the widget."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget(self)

        # --- 1. Main View with Scrollable Gallery and Controls ---
        self.main_content_widget = QWidget()
        content_layout = QVBoxLayout(self.main_content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        self._content_layout = content_layout

        # Scroll area for horizontal gallery
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        # Inner widget holding the horizontal thumbnail layout
        self.gallery_widget = QWidget()
        self.gallery_layout = QHBoxLayout(self.gallery_widget)
        self.gallery_layout.setContentsMargins(4, 4, 4, 4)
        self.gallery_layout.setSpacing(THUMB_SPACING)
        self.gallery_layout.addStretch(1)  # Push thumbnails to the left
        self.gallery_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )

        self.scroll_area.setWidget(self.gallery_widget)

        # Control bar with buttons
        control_bar_layout = QHBoxLayout()
        control_bar_layout.setContentsMargins(5, 0, 5, 0)
        control_bar_layout.setSpacing(5)
        self.index_label = CaptionLabel("0 / 0")
        self.set_cover_button = ToolButton(FluentIcon.PHOTO, self)
        self.set_cover_button.setToolTip("Set as cover image")
        self.set_cover_button.setVisible(False)
        self.add_button = ToolButton(FluentIcon.ADD, self)
        self.add_button.setToolTip("Add image from file...")
        self.paste_button = ToolButton(FluentIcon.PASTE, self)
        self.paste_button.setToolTip("Paste image from clipboard")
        self.remove_button = ToolButton(FluentIcon.DELETE, self)
        self.remove_button.setToolTip("Remove selected image")
        self.clear_all_button = ToolButton(FluentIcon.REMOVE, self)
        self.clear_all_button.setToolTip("Remove all images")
        self.loading_ring = ProgressRing(self)
        self.loading_ring.setFixedSize(16, 16)
        self.loading_ring.setVisible(False)

        control_bar_layout.addWidget(self.index_label, 0, Qt.AlignmentFlag.AlignLeft)
        control_bar_layout.addStretch(1)
        control_bar_layout.addWidget(self.set_cover_button)
        control_bar_layout.addWidget(self.loading_ring)
        control_bar_layout.addWidget(self.add_button)
        control_bar_layout.addWidget(self.paste_button)
        control_bar_layout.addWidget(self.remove_button)
        control_bar_layout.addWidget(self.clear_all_button)

        content_layout.addWidget(self.scroll_area, 1)
        content_layout.addLayout(control_bar_layout)

        # --- 2. Null State View ---
        self.null_state_widget = QWidget(self)
        null_layout = VBoxLayout(self.null_state_widget)
        null_layout.setSpacing(10)
        null_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        info_label = SubtitleLabel("No Preview Images")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("color: grey;")

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.null_add_button = TransparentPushButton(
            FluentIcon.ADD, "Add from File...", self
        )
        self.null_paste_button = TransparentPushButton(FluentIcon.PASTE, "Paste", self)

        button_layout.addStretch(1)
        button_layout.addWidget(self.null_add_button)
        button_layout.addWidget(self.null_paste_button)
        button_layout.addStretch(1)

        null_layout.addStretch(1)
        null_layout.addWidget(info_label)
        null_layout.addLayout(button_layout)
        null_layout.addStretch(1)

        # --- Assemble Stack ---
        self.stack.addWidget(self.main_content_widget)
        self.stack.addWidget(self.null_state_widget)
        main_layout.addWidget(self.stack)
        self.stack.setCurrentWidget(self.null_state_widget)

    def _connect_signals(self):
        self.add_button.clicked.connect(self._on_add_button_clicked)
        self.paste_button.clicked.connect(self._on_paste_button_clicked)
        self.remove_button.clicked.connect(self._on_remove_button_clicked)
        self.clear_all_button.clicked.connect(self._on_clear_all_button_clicked)
        self.set_cover_button.clicked.connect(self._on_set_cover_clicked)

        self.null_add_button.clicked.connect(self._on_add_button_clicked)
        self.null_paste_button.clicked.connect(self._on_paste_button_clicked)

        self.view_model.thumbnail_operation_in_progress.connect(
            self._on_loading_state_changed
        )

    def set_image_paths(self, image_paths: list[Path]):
        """Receives a list of image paths and incrementally updates the gallery.

        Only widgets for removed paths are destroyed; only new paths create
        widgets.  Reused widgets keep their cached pixmap.  Full rebuild is
        triggered only when switching to a completely different mod.
        """
        new_paths = image_paths or []

        # ── Full clear ──────────────────────────────────────────────────────
        if not new_paths:
            self._clear_gallery()
            self._image_paths = []
            self._selected_index = 0
            self.stack.setCurrentWidget(self.null_state_widget)
            self._update_index_label()
            self.set_cover_button.setVisible(False)
            self.updateGeometry()
            return

        # ── Detect full mod switch (completely disjoint path sets) ──────────
        old_str_set = {str(p) for p in self._image_paths}
        new_str_set = {str(p) for p in new_paths}
        is_mod_switch = bool(self._thumb_labels) and old_str_set.isdisjoint(new_str_set)

        if is_mod_switch:
            self._clear_gallery()
            self._image_paths = new_paths
            self._selected_index = 0
            self._build_gallery()
            return

        # ── Incremental update ──────────────────────────────────────────────
        self.stack.setCurrentWidget(self.main_content_widget)

        # Build lookup: str(p) → (index, ThumbnailGalleryLabel)
        old_by_path: dict[str, tuple[int, ThumbnailGalleryLabel]] = {}
        for i, (p, lbl) in enumerate(zip(self._image_paths, self._thumb_labels)):
            old_by_path[str(p)] = (i, lbl)

        # Build new widget list in correct order, reusing existing widgets
        new_labels: list[ThumbnailGalleryLabel] = []
        for i, p in enumerate(new_paths):
            p_str = str(p)
            if p_str in old_by_path:
                _, lbl = old_by_path[p_str]
                lbl.index = i
                new_labels.append(lbl)
            else:
                label = ThumbnailGalleryLabel(p, i, self.gallery_widget)
                label.clicked.connect(self._on_thumbnail_clicked)
                label.doubleClicked.connect(self._on_thumbnail_double_clicked)
                new_labels.append(label)

        # Widgets that existed before but are no longer in the new list
        widgets_to_remove = [
            lbl
            for p, lbl in zip(self._image_paths, self._thumb_labels)
            if str(p) not in new_str_set
        ]
        for lbl in widgets_to_remove:
            self.gallery_layout.removeWidget(lbl)
            self._pixmap_cache.pop(str(lbl.image_path), None)  # evict deleted
            lbl.deleteLater()

        # Remove kept widgets from layout so we can re-insert in new order
        for lbl in self._thumb_labels:
            if lbl not in widgets_to_remove:
                self.gallery_layout.removeWidget(lbl)

        # Re-insert all widgets in correct order (before the trailing stretch)
        for lbl in new_labels:
            self.gallery_layout.insertWidget(
                self.gallery_layout.count() - 1, lbl
            )

        # ── Update state ────────────────────────────────────────────────────
        self._image_paths = new_paths
        self._thumb_labels = new_labels
        self._selected_index = 0

        for lbl in new_labels:
            lbl.set_selected(False)
        if new_labels:
            new_labels[0].set_selected(True)

        self._update_thumb_sizes()
        self._update_index_label()
        self.updateGeometry()

    def _build_gallery(self):
        """Full gallery build from current self._image_paths (no cache clear)."""
        for i, path in enumerate(self._image_paths):
            label = ThumbnailGalleryLabel(path, i, self.gallery_widget)
            label.clicked.connect(self._on_thumbnail_clicked)
            label.doubleClicked.connect(self._on_thumbnail_double_clicked)
            self.gallery_layout.insertWidget(
                self.gallery_layout.count() - 1, label
            )
            self._thumb_labels.append(label)

        if self._thumb_labels:
            self._thumb_labels[0].set_selected(True)

        self._update_thumb_sizes()
        self._update_index_label()
        self.updateGeometry()

    def _clear_gallery(self):
        """Remove all thumbnail labels from the gallery layout (preserves pixmap cache)."""
        for label in self._thumb_labels:
            self.gallery_layout.removeWidget(label)
            label.deleteLater()
        self._thumb_labels.clear()

    def clear_cache(self):
        """Explicitly clear the in-memory pixmap cache (called when images are deleted)."""
        self._pixmap_cache.clear()

    def _update_thumb_sizes(self):
        """Calculate per-image thumbnail sizes based on image aspect ratios."""
        if not self._thumb_labels:
            return

        for label in self._thumb_labels:
            # Check cache first to avoid reloading from disk on resize
            cache_key = str(label.image_path)
            pixmap = self._pixmap_cache.get(cache_key)
            if pixmap is None:
                pixmap = QPixmap(cache_key)
                if pixmap.isNull():
                    label.setFixedSize(THUMB_WIDTH_MIN, THUMB_HEIGHT)
                    continue
                # LRU: evict oldest if at capacity
                if len(self._pixmap_cache) >= self._pixmap_cache_max:
                    self._pixmap_cache.popitem(last=False)
                self._pixmap_cache[cache_key] = pixmap
            else:
                # Mark as recently used (OrderedDict — move to end)
                self._pixmap_cache.move_to_end(cache_key)

            # Calculate width from aspect ratio at fixed height
            w = int(THUMB_HEIGHT * pixmap.width() / pixmap.height())
            w = max(THUMB_WIDTH_MIN, min(w, THUMB_WIDTH_MAX))
            size = QSize(w, THUMB_HEIGHT)

            scaled = pixmap.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            label.set_pixmap(scaled)
            label.setFixedSize(size)

    def _on_thumbnail_clicked(self, index: int):
        """Handle clicking a thumbnail to select it."""
        if index < 0 or index >= len(self._thumb_labels):
            return

        # Deselect all, select the clicked one
        for i, label in enumerate(self._thumb_labels):
            label.set_selected(i == index)
        self._selected_index = index
        self._update_index_label()

        # Scroll to ensure the clicked thumbnail is visible
        if index < len(self._thumb_labels):
            self.scroll_area.ensureWidgetVisible(self._thumb_labels[index])

    def _on_thumbnail_double_clicked(self, index: int):
        """Open a non-modal full-size viewer for the double-clicked image."""
        if index < 0 or index >= len(self._image_paths):
            return
        path = self._image_paths[index]
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return

        # Close existing dialog if any
        if hasattr(self, '_full_size_dialog') and self._full_size_dialog is not None:
            try:
                self._full_size_dialog.close()
            except RuntimeError:
                pass

        dialog = FullSizeImageDialog(pixmap, title=path.name)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()
        self._full_size_dialog = dialog

    def resizeEvent(self, event: QResizeEvent):
        """Recalculate thumbnail sizes when the widget is resized."""
        super().resizeEvent(event)
        self._update_thumb_sizes()

    def sizeHint(self):
        """Return a height that accommodates the full thumbnail row."""
        if not self._image_paths:
            return super().sizeHint()
        gm = self.gallery_layout.contentsMargins()
        h = THUMB_HEIGHT + gm.top() + gm.bottom()  # gallery area
        cl = self._content_layout
        if cl:
            h += cl.spacing()  # gap between gallery and controls
        h += 30  # estimated control bar height
        return QSize(400, h)

    def _update_index_label(self):
        total = len(self._image_paths)
        current = self._selected_index + 1 if total > 0 else 0
        self.index_label.setText(f"{current} / {total}")
        self.set_cover_button.setVisible(total > 1)

    # --- Drag & Drop Events ---

    def dragEnterEvent(self, event: QDragEnterEvent):
        mime_data = event.mimeData()
        if mime_data is not None and mime_data.hasUrls():
            for url in mime_data.urls():
                if url.isLocalFile() and url.toLocalFile().lower().endswith(
                    SUPPORTED_IMAGE_EXTENSIONS
                ):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        mime_data = event.mimeData()
        urls = []
        if mime_data is not None and mime_data.hasUrls():
            urls = [
                url
                for url in mime_data.urls()
                if url.isLocalFile()
                and url.toLocalFile().lower().endswith(SUPPORTED_IMAGE_EXTENSIONS)
            ]

        for url in urls:
            try:
                with open(url.toLocalFile(), "rb") as f:
                    image_data = f.read()
                self.view_model.add_new_thumbnail(image_data)
            except IOError as e:
                InfoBar.error(
                    "File Error",
                    f"Could not read dropped file: {e}",
                    parent=self.window(),
                    position=InfoBarPosition.TOP_RIGHT,
                )
        event.acceptProposedAction()

    # --- Context Menu Event ---
    def contextMenuEvent(self, event: QContextMenuEvent):
        menu = RoundMenu(parent=self)

        add_action = QAction(FluentIcon.ADD.icon(), "Add Image...", self)
        add_action.triggered.connect(self._on_add_button_clicked)
        menu.addAction(add_action)

        paste_action = QAction(FluentIcon.PASTE.icon(), "Paste from Clipboard", self)
        paste_action.triggered.connect(self._on_paste_button_clicked)
        menu.addAction(paste_action)

        if self._image_paths:
            menu.addSeparator()

            if len(self._image_paths) > 1:
                set_cover_action = QAction(
                    FluentIcon.PHOTO.icon(), "Set as Cover", self
                )
                set_cover_action.triggered.connect(self._on_set_cover_clicked)
                menu.addAction(set_cover_action)
                menu.addSeparator()

            remove_action = QAction(
                FluentIcon.DELETE.icon(), "Remove This Image", self
            )
            remove_action.triggered.connect(self._on_remove_button_clicked)
            menu.addAction(remove_action)

            clear_all_action = QAction(
                FluentIcon.REMOVE.icon(), "Clear All Images", self
            )
            clear_all_action.triggered.connect(self._on_clear_all_button_clicked)
            menu.addAction(clear_all_action)

        menu.exec(event.globalPos(), ani=True)

    # --- Button Handlers ---

    def _on_add_button_clicked(self):
        file_names, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Preview Images",
            "",
            f"Image Files ({' '.join(['*' + ext for ext in SUPPORTED_IMAGE_EXTENSIONS])})",
        )

        if not file_names:
            return

        for file_name in file_names:
            try:
                with open(file_name, "rb") as f:
                    image_data = f.read()
                self.view_model.add_new_thumbnail(image_data)
            except IOError as e:
                InfoBar.error(
                    "File Error",
                    f"Could not read image file: {e}",
                    parent=self.window(),
                    position=InfoBarPosition.TOP_RIGHT,
                )

    def _on_paste_button_clicked(self):
        self.view_model.paste_thumbnail_from_clipboard()

    def _on_remove_button_clicked(self):
        if not self._image_paths or not self._thumb_labels:
            return

        if 0 <= self._selected_index < len(self._image_paths):
            path_to_remove = self._image_paths[self._selected_index]

            reply = MessageBox(
                "Confirm Deletion",
                f"Are you sure you want to remove this image?\n({path_to_remove.name})",
                self.window(),
            )
            if reply.exec():
                self.view_model.remove_thumbnail(path_to_remove)

    def _on_clear_all_button_clicked(self):
        if not self._image_paths:
            return

        QTimer.singleShot(0, self._confirm_clear_all)

    def _confirm_clear_all(self):
        """Show confirmation dialog outside the context menu's event loop."""
        reply = MessageBox(
            "Confirm Clear All",
            "Are you sure you want to remove ALL preview images for this mod?",
            self.window(),
        )
        reply.yesButton.setText("Yes, Clear All")
        reply.cancelButton.setText("Cancel")
        if reply.exec():
            self.view_model.remove_all_thumbnails()

    def _on_set_cover_clicked(self):
        """Set the currently selected image as the cover (move to front)."""
        if not self._image_paths or not self._thumb_labels:
            return
        if self._selected_index < 0 or self._selected_index >= len(self._image_paths):
            return
        if self._selected_index == 0:
            return  # Already the cover

        path = self._image_paths[self._selected_index]
        self.view_model.set_preview_image_as_cover(path)

    def _on_loading_state_changed(self, is_loading: bool):
        self.loading_ring.setVisible(is_loading)
        self.add_button.setEnabled(not is_loading)
        self.paste_button.setEnabled(not is_loading)
        self.remove_button.setEnabled(not is_loading)
        self.clear_all_button.setEnabled(not is_loading)
        self.set_cover_button.setEnabled(not is_loading)
