## Why

Internal mod drag-and-drop lacks any visual feedback: the cursor stays a plain
arrow throughout the drag, drop targets give no hover hint, and there is no way
to drop a mod into an *ancestor* directory — only into a navigable subfolder or
another mod's character root. This makes reorganizing mods across the hierarchy
both unintuitive and functionally limited.

## What Changes

- Drag source (`FolderGridItemWidget.mouseMoveEvent`) sets a custom drag
  pixmap from the mod's first preview thumbnail (card grab snapshot as
  fallback) and a `DragMoveCursor` override, so the dragged mod is visually
  represented and the cursor reflects the drag on every region of the app.
- Drop targets (`FolderGridItemWidget`, `ObjectListItemWidget`) gain a
  `dragMoveEvent` override that calls `acceptProposedAction()`, making the
  move cursor stable over accepted targets instead of flickering to the
  default arrow.
- `BreadcrumbWidget` becomes a drop target for `EMMM_MOD_MIME_TYPE` drags.
  Each ancestor breadcrumb segment (all but the current/last segment) accepts
  a dropped mod and moves it into that segment's directory, surfaced via a new
  `drop_requested(item_id, Path)` signal wired to
  `ModListViewModel.move_item_to_folder`.
- The current/last breadcrumb segment rejects the drop (mod is already there)
  and shows the forbidden cursor; gaps and non-drop regions surface the
  forbidden cursor via Qt's default for an ignored `dragMoveEvent`.
- Hovered ancestor segment lights up (reuses `BreadcrumbItem.isHover`) as
  immediate feedback while dragging over it.

## Capabilities

### New Capabilities

- `breadcrumb-drop-target`: Breadcrumb widget accepts internal mod drags and
  routes them into ancestor directories via a `drop_requested` signal;
  defines hit-testing, hover highlight, current-segment rejection, and
  cursor/feedback behavior.

### Modified Capabilities

- `views`: Drag source sets a custom pixmap and override cursor; drop targets
  implement `dragMoveEvent` for stable move-cursor feedback. Section
  "Drag-and-drop (internal)" of `views.md` gains these requirements.

## Impact

- **Code:**
  - `app/views/components/foldergrid_widget.py` — source pixmap + override
    cursor in `mouseMoveEvent`; `dragMoveEvent` override for drop targets.
  - `app/views/components/breadcrumb_widget.py` — `setAcceptDrops(True)`,
    `dragEnterEvent`/`dragMoveEvent`/`dragLeaveEvent`/`dropEvent`, new
    `drop_requested` signal.
  - `app/views/components/objectlist_widget.py` — `dragMoveEvent` override.
  - `app/views/sections/foldergrid_panel.py` — wire
    `breadcrumb_widget.drop_requested` → `view_model.move_item_to_folder`.
- **APIs/Signals:** New `BreadcrumbWidget.drop_requested(str, object)`.
  Reuses existing `ModListViewModel.move_item_to_folder(item_id, target_path)`
  — no new service or VM method.
- **Dependencies:** None added. Uses only PyQt6 / qfluentwidgets APIs already
  in the project.
- **Specs:** Adds `specs/breadcrumb-drop-target/spec.md`; amends
  `specs/views.md` drag-and-drop section via delta.
- **Risks:** None breaking. Existing external-file import path on
  `FolderGridPanel` and image-drop on `ThumbnailWidget` are untouched.