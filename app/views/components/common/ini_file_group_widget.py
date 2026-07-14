# app/views/components/ini_file_group_widget.py
from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout as _QVBoxLayout,
)
from qfluentwidgets import (
    StrongBodyLabel,
    TransparentToolButton,
    FluentIcon,
    VBoxLayout,
)
from app.core import i18n as _i18n


class IniFileGroupWidget(QFrame):
    """Card-style container for a collection of keybindingwidgets one file."""

    open_file_requested = pyqtSignal(Path)

    def __init__(self, title: str, file_path: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.file_path = file_path
        self._init_ui(title)

    # app/views/components/ini_file_group_widget.py
    def _init_ui(self, title: str) -> None:
        self.setObjectName("IniFileGroup")
        self.setStyleSheet(
            """
            #IniFileGroup {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 6px;
            }
            #IniFileGroup QWidget, #IniFileGroup QFrame, #IniFileGroup QLabel { min-width: 0; }
            """
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # main vertical layout
        main = VBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # ── header ───────────────────────────────────────────────────────────
        header = QWidget(self)
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 8, 8, 8)
        h.setSpacing(8)

        self.title_label = StrongBodyLabel(title, self)
        self.title_label.setWordWrap(True)
        self.title_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        h.addWidget(self.title_label)
        h.addStretch(1)

        open_btn = TransparentToolButton(FluentIcon.PENCIL_INK, self)
        open_btn.setFixedSize(24, 24)  # konsisten & tidak melar
        open_btn.setToolTip(_i18n.tr("ini_group.open_tooltip", name=self.file_path.name))
        open_btn.clicked.connect(lambda: self.open_file_requested.emit(self.file_path))
        h.addWidget(open_btn, 0, Qt.AlignmentFlag.AlignRight)
        main.addWidget(header)

        # ── separator ────────────────────────────────────────────────────────
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        main.addWidget(sep)

        # ── content container ────────────────────────────────────────────────
        content = QWidget(self)
        content.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.content_layout = VBoxLayout(content)
        self.content_layout.setContentsMargins(8, 8, 8, 12)
        self.content_layout.setSpacing(10)
        main.addWidget(content)

    # ──────────────────────────────────────────────────────────────────────────
    def add_binding_widget(self, widget: QWidget) -> None:
        """Add keybinding widget with a visual separator before it (except the first)."""
        if self.content_layout.count() > 0:
            sep = QFrame(self)
            sep.setFixedHeight(1)
            sep.setStyleSheet("background-color: rgba(255,255,255,0.08); border: none;")
            self.content_layout.addWidget(sep)
        self.content_layout.addWidget(widget)
