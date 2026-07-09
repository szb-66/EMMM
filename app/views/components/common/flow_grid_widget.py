# app/views/components/common/flow_grid_widget.py
from PyQt6.QtWidgets import QWidget
from qfluentwidgets import FlowLayout


class FlowGridWidget(QWidget):
    """A widget that displays other widgets in a responsive flow layout."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("FlowGridContentWidget")

        # The FlowLayout is the main layout for this widget
        self.flowLayout = FlowLayout(self, needAni=False)
        self.flowLayout.setContentsMargins(12, 12, 12, 12)
        self.flowLayout.setVerticalSpacing(15)
        self.flowLayout.setHorizontalSpacing(15)

    def add_widget(self, widget: QWidget):
        """Adds a widget to the flow layout.

        Explicitly shows the widget: ``clear_items`` hides every detached
        widget so stale geometry doesn't paint. The panel's reuse path then
        re-adds kept widgets here — without ``show()`` they'd stay hidden
        and the grid would render empty even though ``_items`` is populated.
        """
        self.flowLayout.addWidget(widget)
        try:
            widget.show()
        except Exception:
            pass

    def clear_items(self):
        """
        Detaches every widget from the flow layout WITHOUT destroying it.

        Contract with the panel (``_on_items_updated``): widgets that are
        still in the new data set must remain alive so the panel can call
        ``set_data`` on them and re-add them to the layout (the "widget
        reuse" diff path). The panel owns the widget lifecycle and will
        ``deleteLater()`` only the widgets that are truly gone.

        Implementation notes
        --------------------
        We must not call the upstream ``FlowLayout.takeAllWidgets()``: it
        ``deleteLater()``‑izes every widget, which breaks the reuse contract
        (kept widgets end up dead → ``set_data`` is a no‑op → the grid
        appears empty after a toggle). Its backing ``takeAt()`` also has a
        PyQt6 incompat bug (returns ``QWidget`` instead of ``QLayoutItem``)
        that hard‑crashes the app; the monkey‑patch in ``main.py`` fixes the
        crash but not the destroy‑all semantic.

        We also avoid ``widget.setParent(None)``: reparenting a layout‑managed
        child synchronously drives Qt back into ``takeAt`` and the buggy
        reflow path. Instead we:
          1. Snapshot ``_items`` and clear the list (layout thinks it's empty).
          2. Stop & detach any per‑widget 'flowAni' animation.
          3. ``hide()`` each widget so it stops painting at its stale
             geometry. It stays a child of this FlowGridWidget (no reflow
             triggered), ready to be re‑added by the panel.
        The panel's diff logic will ``show()``/re‑add the kept widgets and
        ``deleteLater()`` the removed ones on the next iteration.
        """
        layout = self.flowLayout

        items = list(getattr(layout, "_items", []))
        ani_group = getattr(layout, "_aniGroup", None)

        for item in items:
            widget = None
            try:
                widget = item.widget()
            except Exception:
                widget = None

            # Stop & drop the per-widget 'flowAni' animation if present
            # (needAni=False in our usage, but stay robust against upstream
            # changes — leaving a dangling animation pointing at a widget
            # that the panel is about to re‑parent causes native asserts).
            ani = None
            if widget is not None:
                try:
                    ani = widget.property("flowAni")
                except Exception:
                    ani = None
            if ani is not None:
                try:
                    ani.stop()
                except Exception:
                    pass
                if ani_group is not None:
                    try:
                        ani_group.removeAnimation(ani)
                    except Exception:
                        pass
                try:
                    ani.deleteLater()
                except Exception:
                    pass
                anis = getattr(layout, "_anis", None)
                if isinstance(anis, list):
                    try:
                        anis.remove(ani)
                    except ValueError:
                        pass

            # Hide so the widget stops painting at stale geometry; the
            # panel's re‑add path will show() it again via add_widget().
            if widget is not None:
                try:
                    widget.hide()
                except Exception:
                    pass

        # Drop our reference to the items list so the layout reports empty
        # immediately. The widgets themselves stay alive (still children of
        # this FlowGridWidget, just hidden & unmanaged) until the panel
        # decides their fate.
        if hasattr(layout, "_items"):
            layout._items.clear()