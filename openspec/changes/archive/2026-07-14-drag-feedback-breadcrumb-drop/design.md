## Context

EMMM is a PyQt6 + qfluentwidgets desktop app for managing game mods organized
under per-character directories. Mods are arranged in a center `FolderGridPanel`
as `FolderGridItemWidget` cards; a `BreadcrumbWidget` (wrapping
`BreadcrumbBar`) shows the current directory path as clickable segments whose
paths are tracked in `_segment_paths`.

Internal mod drag-and-drop today uses a custom MIME type `EMMM_MOD_MIME_TYPE`
carrying the mod's `item_id`. Three drop paths exist: card → navigable
subfolder, card → sibling mod (auto-group), card → character row on the left
panel. Each path overrides only `dragEnterEvent` and `dropEvent`; none
implements `dragMoveEvent`, none sets a drag pixmap, and none touches the
cursor, so during a drag the cursor stays the default arrow and accepted
targets give no hover hint.

There is currently no way to move a mod into an *ancestor* directory: the
breadcrumb is purely a click-to-navigate widget. The user wants the breadcrumb
to also act as a drop target for ancestor moves, and overall drag UX needs
visual feedback.

## Goals / Non-Goals

**Goals:**
- Visual drag representation: a custom pixmap on the drag cursor built from
  the mod's first preview thumbnail (card snapshot as fallback).
- Stable move cursor over every drop target during the drag (no flicker to
  the default arrow over the accepted target's area).
- Forbidden/copy cursor surfaced by Qt over non-drop and no-op regions without
  custom painting.
- Breadcrumb as a drop target for ancestor-directory moves, with hover
  highlight on the segment under the cursor and explicit rejection of the
  current/last segment (mod already there).
- Reuse the existing `ModListViewModel.move_item_to_folder(item_id, path)` and
  the existing `EMMM_MOD_MIME_TYPE` channel — no new service, no new VM method,
  no new MIME type.

**Non-Goals:**
- Multi-select drag (dragging more than one mod at once).
- Reordering mods within the same folder by drag (sort is handled elsewhere).
- Drop-to-rename via the breadcrumb.
- Any change to the external-file import path or the thumbnail image-drop path.
- Persisting drag feedback state across sessions.

## Decisions

### D1 — Single `QApplication.setOverrideCursor(DragMoveCursor)` around `drag.exec`
**Rationale:** Gives a guaranteed move cursor for the whole drag even over
regions whose `dragMoveEvent` rejects — Qt's interpreted cursor is governed by
the last accepted/ignored `dragMoveEvent`; while the override is active it
wins over the interpreted shape. Pair with `restoreOverrideCursor()` in a
`finally` so a rare `drag.exec` exception cannot pin the cursor.
**Alternative considered:** Setting `setDragEnabled`/cursor only on each
target — rejected: it leaves non-target regions showing the arrow, which is
the exact complaint. One override covers both "over target" and "over gap".

### D2 — Custom pixmap from first preview thumbnail, card `grab()` fallback
**Rationale:** The dragged card's thumbnail is the most recognizable avatar of
the mod; falling back to `self.grab()` keeps the pixmap non-empty when the
mod has no preview images yet. `drag.setHotSpot(QPoint(w//2, h//2))` centers it
under the cursor. Pixmap is capped to ~96 px on the long edge so it never
dominates the screen.
**Alternative considered:** Always `self.grab()` of the full card — rejected
as too large; the proposed fallback is the same path so the cheap code wins.

### D3 — `dragMoveEvent` override on every current drop target
**Rationale:** Qt only switches to the move/copy cursor shape when the most
recent `dragMoveEvent` for the widget under the cursor calls
`acceptProposedAction()`. Today only `dragEnterEvent` accepts, so moving
across the target between `dragEnterEvent` and `dropEvent` falls back to the
default arrow — the observed "plain pointer" bug. The fix is a one-line
override mirroring the enter acceptance.
**Alternative considered:** Setting `Qt.DropAction.MoveAction` as default on
the widget — Qt does not expose such a per-widget default; `dragMoveEvent`
is the documented hook.

### D4 — Breadcrumb becomes a drop target, ancestor segments only
**Rationale:** The breadcrumb already maintains `_segment_paths` parallel to
`BreadcrumbBar.items` with each cumulative path; reusing them as drop targets
is a near-zero-data change. The last/current segment indexes the directory the
mod is already visible in, so dropping there is a no-op and SHALL be rejected
with the default forbidden cursor (Qt renders `ignore()` as forbidden). All
strictly-ancestor segments (indices `< len-1`) accept and route through the
new `drop_requested(item_id, Path)` signal to `move_item_to_folder`.
**Alternative considered:** Accept the current segment and emit a no-op
toast — rejected: the no-op is meaningless and silently accepting trains the
user that the breadcrumb always takes drops. Forbidden feedback is clearer.
**Alternative considered:** Rebuild the breadcrumb as a custom painted widget
with per-segment drop indicators — rejected: reuses an existing dependency
(`qfluentwidgets.BreadcrumbBar`) and its existing `isHover` paint branch; no
painting of our own is needed for the hover state.

### D5 — Hit-test via `BreadcrumbItem.geometry().contains()` on `dragMoveEvent`
**Rationale:** `BreadcrumbBar.items` are real `QWidget`s with set geometries;
a per-segment `geometry().contains(pos)` scan in `dragMoveEvent` is O(segments)
≤ ~8 and far simpler than installing event filters on each item. Hidden items
(`isVisible()==False`) and `elideButton` are skipped. The previously hovered
segment has `isHover=False; update()` reset on each move so highlight tracks
the cursor exactly.
**Alternative considered:** `installEventFilter` per `BreadcrumbItem` —
rejected: more wiring, same result, and `BreadcrumbItem` already repaints on
`isHover` change via its `paintEvent` opacity branch.
**Ponytail note:** Linear scan over ≤ ~8 segments is O(n) on every
`dragMoveEvent`; if the trail ever grows into the dozens (very deep folders),
switch to a precomputed `[(rect, index)]` list rebuilt in `_build_from_path`.
For now the scan is invisible at 60 Hz.

### D6 — Hover highlight reuses `BreadcrumbItem.isHover`
**Rationale:** `BreadcrumbItem.paintEvent` already differentiates
`isSelected or isHover` with full opacity. Setting `isHover=True; update()` on
the hit item produces the same look as a mouse hover, so drag-over feels like a
real hover instead of inventing new styling. Reset the previous item's
`isHover=False` when the hit changes or on `dragLeaveEvent`/`dropEvent`.
**Alternative considered:** A custom `isDropHover` property with its own paint
branch — rejected: extra code for an indistinguishable visual.

### D7 — Wiring kept at the panel level, no new VM method
**Rationale:** `BreadcrumbWidget.drop_requested(item_id, Path)` is connected in
`foldergrid_panel.py` to `self.view_model.move_item_to_folder`, the exact same
slot `FolderGridItemWidget.dropEvent` already calls. No service-layer or
viewmodel-layer change is needed. Keeping the signal at the panel-wiring level
matches the existing pattern for `navigation_requested` (panel → VM.

## Risks / Trade-offs

- **Override cursor not restored on hard crash inside `drag.exec`** →
  Mitigation: wrap in `try/finally` calling `restoreOverrideCursor()`.
- **`_segment_paths` staleness during an active drag** (the breadcrumb can be
  rebuilt by a concurrent `path_changed` mid-drag) → Mitigation: resolve the
  target path *at drop time* from the index still held in `_hover_index`; if
  the index is out of range relative to the rebuilt `_segment_paths`, ignore
  the drop rather than moving to the wrong path.
- **Hit-test false negs because `BreadcrumbBar` maps differently than
  `BreadcrumbWidget`** → Mitigation: convert cursor pos with
  `self.breadcrumb.mapFrom(self, event.position().toPoint())` before testing
  item geometries; verified during implementation by stepping through one
  segment width example.
- **Forbidden cursor over the current segment could read as "broken" rather
  than "no-op"** → Mitigation: the hover highlight only fires on ancestor
  segments, so there is no visual promise of a drop on the last segment; the
  forbidden cursor is consistent with that.
- **Existing reuse-widgets-on-update requirement (`views.md:108`) could
  interact with drop highlight state if a drag is in flight when
  `items_updated` fires** → Mitigation: breadcrumb items are owned by
  `BreadcrumbBar`, not the grid-reuse path; the grids' `FolderGridItemWidget`
  reuse path does not hold drag state across rebuilds because the override
  cursor lives on `QApplication`, not on the widget.