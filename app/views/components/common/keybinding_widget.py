# app/views/components/keybinding_widget.py

from typing import List, Dict
from pathlib import Path

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QFormLayout,
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
    VBoxLayout,
    SpinBox,
    FlowLayout,
    FluentIcon,
)

from app.services.Iniparsing_service import KeyBinding, Assignment

# ---------- constants ----------
ROW_MARGINS = (4, 0, 4, 0)
HEADER_MARGIN = (4, 8, 4, 8)
SPACING_V = 8
FIELD_STRETCH = 3  # label:field proportion when space is plentiful


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
        """Build widget UI – vertical list, label-left field-right, fluent widgets."""
        # global
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setStyleSheet("QLineEdit,QComboBox,QSpinBox{min-width:0;}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SPACING_V)

        # ── header ────────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(*HEADER_MARGIN)
        header.addWidget(StrongBodyLabel(self.binding_data.section_name))
        header.addStretch(1)
        if self.binding_data.condition:
            header.addWidget(CaptionLabel(f"if: {self.binding_data.condition}"))
        root.addLayout(header)

        # ── note row ──────────────────────────────────────────────────────────────
        self.note_edit = LineEdit()
        self.note_edit.setPlaceholderText("Add a note…")
        self.note_edit.setText(self.binding_data.note)
        root.addLayout(self._create_row("Note", self.note_edit))

        # ── assignments ───────────────────────────────────────────────────────────
        for a in self.binding_data.assignments:
            field = self._create_smart_input(a)
            self.assignment_widgets[a.variable] = field
            root.addLayout(self._create_row(a.variable, field))

        # ── triggers (keys / backs) ───────────────────────────────────────────────
        if self.binding_data.keys or self.binding_data.backs:
            if self.binding_data.assignments:
                root.addWidget(self._hline())

            for i, val in enumerate(self.binding_data.keys, 1):
                edit = self._line_edit(val)
                self.key_edits.append(edit)
                root.addLayout(self._create_row(f"Key", edit))

            for i, val in enumerate(self.binding_data.backs, 1):
                edit = self._line_edit(val)
                self.back_edits.append(edit)
                root.addLayout(self._create_row(f"Back", edit))

        self.setLayout(root)

    # ── helpers ──────────────────────────────────────────────────────────────────
    def _create_row(self, text: str, field: QWidget) -> QHBoxLayout:
        """Return HBox: [label][field] with field taking extra space."""
        row = QHBoxLayout()
        row.setContentsMargins(*ROW_MARGINS)
        row.setSpacing(6)

        lbl = BodyLabel(f"{text}:")
        lbl.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)

        field.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        row.addWidget(lbl)
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
        return ln

    def _create_assignment_row(self, assignment: Assignment) -> QWidget:
        """Row: [label][field] with field taking extra space."""
        container = QWidget(self)
        container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        row = QHBoxLayout()
        row.setContentsMargins(*ROW_MARGINS)
        row.setSpacing(SPACING_V)

        lbl = BodyLabel(f"{assignment.variable}:")
        lbl.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        row.addWidget(lbl)

        field = self._create_smart_input(assignment)
        field.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.assignment_widgets[assignment.variable] = field
        row.addWidget(field, FIELD_STRETCH)

        container.setLayout(row)
        return container

    def _create_smart_input(self, assignment: Assignment) -> QWidget:
        """ComboBox with cycle_options, compressible in narrow panels."""

        cb = ComboBox(self)
        cb.setStyleSheet(
            "QComboBox{min-width:0; padding:2px 4px;}"
            "QComboBox::drop-down{width:16px;}"
        )
        cb.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        if assignment.cycle_options:
            cb.addItems(assignment.cycle_options)
        cb.setCurrentText(
            assignment.current_value
            or (assignment.cycle_options[0] if assignment.cycle_options else "")
        )
        return cb

    def _create_trigger_row(
        self,
        parent_layout: QVBoxLayout,
        label: str,
        values: list[str],
        widget_list: list[LineEdit],
    ) -> None:
        """Add trigger rows ke parent_layout."""

        for idx, val in enumerate(values, 1):
            row = QWidget(self)
            row.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )

            h = QHBoxLayout()
            h.setContentsMargins(*ROW_MARGINS)
            h.setSpacing(SPACING_V)

            cap = CaptionLabel(f"{label} {idx}:")
            cap.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
            h.addWidget(cap)

            edit = LineEdit(self)
            edit.setText(val)
            edit.setStyleSheet("min-width:0;")
            widget_list.append(edit)
            h.addWidget(edit, FIELD_STRETCH)

            row.setLayout(h)
            parent_layout.addWidget(row)

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
