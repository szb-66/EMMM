# app/views/components/breadcrumb_widget.py
# A navigation widget that displays the current folder path as clickable segments.

from __future__ import annotations
from pathlib import Path
from typing import List

from PyQt6.QtWidgets import QWidget, QHBoxLayout
from PyQt6.QtCore import pyqtSignal, Qt, QByteArray
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDragLeaveEvent, QDropEvent
from qfluentwidgets import BreadcrumbBar
from app.utils.logger_utils import logger
from app.core.constants import EMMM_MOD_MIME_TYPE


class BreadcrumbWidget(QWidget):
    """
    A navigation widget that displays a clickable folder path.
    It intelligently handles root path changes.
    """

    navigation_requested = pyqtSignal(Path)
    drop_requested = pyqtSignal(str, object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.root_path: Path | None = None
        self._segment_paths: List[Path] = []
        self._hover_index: int | None = None
        self._init_ui()

    def _init_ui(self):
        """Initializes the UI components of the widget."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        self.breadcrumb = BreadcrumbBar(self)
        self.breadcrumb.currentIndexChanged.connect(self._on_segment_clicked)
        main_layout.addWidget(self.breadcrumb)
        self.setAcceptDrops(True)

    def _build_from_path(self, current_path: Path):
        """Private helper to rebuild the UI from a given path and the current root."""
        self.breadcrumb.blockSignals(True)
        self.breadcrumb.clear()
        self._segment_paths.clear()

        if not self.root_path:
            self.breadcrumb.blockSignals(False)
            return

        # Add the root segment, which is always the first item
        self.breadcrumb.addItem(routeKey="root", text=self.root_path.name)
        self._segment_paths.append(self.root_path)

        # Add sub-segments if the current path is deeper than the root
        if current_path != self.root_path:
            try:
                relative_path = current_path.relative_to(self.root_path)
                cumulative_path = self.root_path
                for i, part in enumerate(relative_path.parts):
                    cumulative_path = cumulative_path / part
                    self._segment_paths.append(cumulative_path)
                    self.breadcrumb.addItem(routeKey=str(i + 1), text=part)
            except ValueError:
                # This should not happen due to the logic in set_current_path,
                # but it's a safe fallback.
                logger.error(
                    f"Path error: Could not find relation between '{current_path}' and root '{self.root_path}'"
                )
                self.clear()  # Clear the breadcrumb on error
                return

        self.breadcrumb.setCurrentIndex(len(self._segment_paths) - 1)
        self.breadcrumb.blockSignals(False)

    def _on_segment_clicked(self, index: int):
        """Emits the full path of the clicked segment."""
        if 0 <= index < len(self._segment_paths):
            path_to_navigate = self._segment_paths[index]
            self.navigation_requested.emit(path_to_navigate)

    # --- Drag-and-drop support (ancestor-directory moves) ---

    def _clear_hover(self):
        if self._hover_index is not None and 0 <= self._hover_index < len(self.breadcrumb.items):
            item = self.breadcrumb.items[self._hover_index]
            item.isHover = False
            item.update()
        self._hover_index = None

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat(EMMM_MOD_MIME_TYPE):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent):
        if not event.mimeData().hasFormat(EMMM_MOD_MIME_TYPE):
            super().dragMoveEvent(event)
            return

        # ponytail: linear scan over ≤ ~8 breadcrumb segments per dragMoveEvent;
        # if deep folders ever push this higher, precompute a [(rect, index)] list
        # in _build_from_path and reuse it here.
        pos = self.breadcrumb.mapFrom(self, event.position().toPoint())
        last_index = len(self._segment_paths) - 1
        hit_index = None
        for i, item in enumerate(self.breadcrumb.items):
            if not item.isVisible():
                continue
            # skip the elideButton (it's not a BreadcrumbItem — no index attr)
            if not hasattr(item, "index"):
                continue
            if item.geometry().contains(pos):
                if i < last_index:
                    hit_index = i
                break

        if hit_index is not None:
            if self._hover_index != hit_index:
                self._clear_hover()
                self._hover_index = hit_index
                self.breadcrumb.items[hit_index].isHover = True
                self.breadcrumb.items[hit_index].update()
            event.acceptProposedAction()
        else:
            self._clear_hover()
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self._clear_hover()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        mime = event.mimeData()
        if not mime.hasFormat(EMMM_MOD_MIME_TYPE):
            super().dropEvent(event)
            return

        hover = self._hover_index
        self._clear_hover()

        if hover is None or hover >= len(self._segment_paths) - 1:
            event.ignore()
            return

        dropped_id = bytes(mime.data(EMMM_MOD_MIME_TYPE)).decode("utf-8")
        if not dropped_id:
            event.ignore()
            return

        self.drop_requested.emit(dropped_id, self._segment_paths[hover])
        event.acceptProposedAction()

    # --- Public Methods ---

    def set_current_path(self, path: Path | None):
        """
        The main method to update the breadcrumb.
        It intelligently resets the root if the new path is not a sub-path
        of the old root, preventing navigation errors.
        """
        if not path or not path.is_dir():
            self.clear()
            return

        is_subpath = True
        if self.root_path:
            try:
                # Check if the new path is a descendant of the current root
                path.relative_to(self.root_path)
            except ValueError:
                is_subpath = False

        # If there is no root, or if the new path is not a sub-path,
        # it signifies a context switch (e.g., new ObjectItem selected).
        # We must reset the root path to this new path.
        if not self.root_path or not is_subpath:
            self.root_path = path

        # Now, rebuild the UI with a guaranteed correct root
        self._build_from_path(path)

    def clear(self):
        """Clears all segments and resets the root path."""
        self.breadcrumb.blockSignals(True)
        self.breadcrumb.clear()
        self._segment_paths.clear()
        self.root_path = None
        self.breadcrumb.blockSignals(False)
