# app/views/components/keybinding_widget.py

from typing import List, Dict

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QWidget,
    QFrame,
    QHBoxLayout,
    QSizePolicy,
)

from qfluentwidgets import (
    BodyLabel,
    LineEdit,
    ComboBox,
    StrongBodyLabel,
    CaptionLabel,
    SpinBox,
)

from app.services.Iniparsing_service import KeyBinding, Assignment
from app.core import i18n as _i18n

# ---------- constants ----------
ROW_MARGINS = (0, 0, 0, 0)
HEADER_MARGIN = (0, 0, 4, 0)
SPACING_V = 6
FIELD_STRETCH = 3  # label:field proportion when space is plentiful
CARD_PADDING = 12
SECTION_SPACING = 8


class KeyBindingWidget(QWidget):
    """
    A widget to display and edit a single key binding entry.
    This version has a robust layout structure to prevent parenting errors.
    """

    value_changed = pyqtSignal(str, str, object, str)

    def __init__(self, binding_data: KeyBinding, parent: QWidget | None = None):
        super().__init__(parent)
        self.binding_data = binding_data
        self.binding_id = self.binding_data.binding_id

        self.key_edits: List[LineEdit] = []
        self.back_edits: List[LineEdit] = []
        self.assignment_widgets: Dict[str, QWidget] = {}

        self._init_ui()
        self._connect_signals()

    def _init_ui(self) -> None:
        """Build widget UI – card-style with background, padding, and visual hierarchy."""
        # ── card styling ──────────────────────────────────────────────────────────
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setStyleSheet("""
            KeyBindingWidget {
                background-color: rgba(255, 255, 255, 0.10);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 8px;
            }
            KeyBindingWidget:hover {
                border: 1px solid rgba(255, 255, 255, 0.22);
                background-color: rgba(255, 255, 255, 0.14);
            }
            KeyBindingWidget QLineEdit, KeyBindingWidget QSpinBox {
                background-color: rgba(255, 255, 255, 0.15);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                padding: 2px 6px;
                min-width: 0;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        root.setSpacing(SECTION_SPACING)

        # ── header ────────────────────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet("background: transparent; border: none;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(*HEADER_MARGIN)
        h_layout.setSpacing(8)

        section_label = StrongBodyLabel(self.binding_data.section_name)
        section_label.setWordWrap(True)
        h_layout.addWidget(section_label)
        h_layout.addStretch(1)

        if self.binding_data.condition:
            cond_label = CaptionLabel(_i18n.tr("keybinding.if_cond", condition=self.binding_data.condition))
            cond_label.setStyleSheet("background: transparent; border: none;")
            h_layout.addWidget(cond_label)

        root.addWidget(header)

        # ── note row ──────────────────────────────────────────────────────────────
        self.note_edit = LineEdit()
        self.note_edit.setPlaceholderText(_i18n.tr("keybinding.note_placeholder"))
        self.note_edit.setText(self.binding_data.note)
        root.addLayout(self._create_row(_i18n.tr("keybinding.note"), self.note_edit))

        # ── assignments ───────────────────────────────────────────────────────────
        if self.binding_data.assignments:
            assignment_section = QWidget()
            assignment_section.setStyleSheet("background: transparent; border: none;")
            as_layout = QVBoxLayout(assignment_section)
            as_layout.setContentsMargins(0, 0, 0, 0)
            as_layout.setSpacing(SPACING_V)

            for a in self.binding_data.assignments:
                field = self._create_smart_input(a)
                self.assignment_widgets[a.variable] = field
                as_layout.addLayout(self._create_row(a.variable, field))

            root.addWidget(assignment_section)

        # ── triggers (keys / backs) ───────────────────────────────────────────────
        if self.binding_data.keys or self.binding_data.backs:
            if self.binding_data.assignments:
                root.addWidget(self._hline())

            trigger_section = QWidget()
            trigger_section.setStyleSheet("background: transparent; border: none;")
            tr_layout = QVBoxLayout(trigger_section)
            tr_layout.setContentsMargins(0, 0, 0, 0)
            tr_layout.setSpacing(SPACING_V)

            for val in self.binding_data.keys:
                edit = self._line_edit(val)
                self.key_edits.append(edit)
                tr_layout.addLayout(self._create_row(_i18n.tr("keybinding.key"), edit))

            for val in self.binding_data.backs:
                edit = self._line_edit(val)
                self.back_edits.append(edit)
                tr_layout.addLayout(self._create_row(_i18n.tr("keybinding.back"), edit))

            root.addWidget(trigger_section)

        self.setLayout(root)

    # ── helpers ──────────────────────────────────────────────────────────────────
    def _create_row(self, text: str, field: QWidget) -> QHBoxLayout:
        """Return HBox: [label][field] with field taking extra space."""
        row = QHBoxLayout()
        row.setContentsMargins(*ROW_MARGINS)
        row.setSpacing(8)

        lbl = BodyLabel(_i18n.tr("keybinding.field_label", text=text))
        lbl.setWordWrap(True)
        lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        lbl.setStyleSheet("background: transparent; border: none; color: rgba(255,255,255,0.7);")

        field.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        row.addWidget(lbl, 1)
        row.addWidget(field, FIELD_STRETCH)
        return row

    def _line_edit(self, text: str) -> LineEdit:
        le = LineEdit()
        le.setText(text)
        return le

    def _hline(self) -> QFrame:
        ln = QFrame()
        ln.setFrameShape(QFrame.Shape.HLine)
        ln.setFrameShadow(QFrame.Shadow.Sunken)
        ln.setStyleSheet("background: transparent; border: none;")
        return ln

    def _create_smart_input(self, assignment: Assignment) -> QWidget:
        """ComboBox with cycle_options, compressible in narrow panels."""

        cb = ComboBox(self)
        cb.setStyleSheet(
            "QComboBox{min-width:0; padding:2px 6px; background-color: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px;}"
            "QComboBox::drop-down{width:16px; border:none;}"
        )
        cb.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        if assignment.cycle_options:
            cb.addItems(assignment.cycle_options)
        cb.setCurrentText(
            assignment.current_value
            or (assignment.cycle_options[0] if assignment.cycle_options else "")
        )
        return cb

    def _connect_signals(self):
        self.note_edit.textChanged.connect(
            lambda text: self.value_changed.emit(
                self.binding_id, "note", "", text
            )
        )
        for i, edit in enumerate(self.key_edits):
            edit.textChanged.connect(
                lambda text, index=i: self.value_changed.emit(
                    self.binding_id, "key", index, text
                )
            )
        for i, edit in enumerate(self.back_edits):
            edit.textChanged.connect(
                lambda text, index=i: self.value_changed.emit(
                    self.binding_id, "back", index, text
                )
            )
        for var, widget in self.assignment_widgets.items():
            if isinstance(widget, ComboBox):
                widget.currentTextChanged.connect(
                    lambda text, v=var: self.value_changed.emit(
                        self.binding_id, "assignment", v, text
                    )
                )
            elif isinstance(widget, SpinBox):
                widget.valueChanged.connect(
                    lambda val, v=var: self.value_changed.emit(
                        self.binding_id, "assignment", v, str(val)
                    )
                )
