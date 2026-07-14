## ADDED Requirements

### Requirement: Drag source shows a custom pixmap and stable move cursor

`FolderGridItemWidget.mouseMoveEvent` SHALL set a custom drag pixmap on the
`QDrag` constructed from the dragged mod's first preview thumbnail, capped to
a sane size on the long edge, with the hotspot centered. When the mod has no
usable preview thumbnail, it SHALL fall back to a `self.grab()` snapshot of
the card. The drag source SHALL install a `DragMoveCursor` override on
`QApplication` for the duration of `drag.exec(...)` and SHALL restore the
previous cursor afterwards, including on exception, so the cursor reflects the
drag on every region of the application rather than reverting to the default
arrow.

#### Scenario: Dragging a mod with thumbnails shows its thumbnail as the pixmap

- **WHEN** the user starts dragging a mod card whose `preview_images` contains
  at least one image
- **THEN** `QDrag.setPixmap` SHALL be called with a `QPixmap` built from that
  image
- **AND** `QDrag.setHotSpot` SHALL center the pixmap under the cursor
- **AND** the application cursor SHALL be the move cursor for the whole drag

#### Scenario: Dragging a mod without thumbnails falls back to the card snapshot

- **WHEN** the user starts dragging a mod card whose `preview_images` is empty
  or unreadable
- **THEN** `QDrag.setPixmap` SHALL be called with a `QPixmap` produced by
  `self.grab()`
- **AND** the drag SHALL otherwise behave identically

#### Scenario: Override cursor is always restored

- **WHEN** `drag.exec(...)` returns normally or raises
- **THEN** `QApplication.restoreOverrideCursor()` SHALL have been called
- **AND** the application cursor SHALL be back to its pre-drag shape

### Requirement: Drop targets implement dragMoveEvent for stable move cursor

`FolderGridItemWidget` and `ObjectListItemWidget` SHALL override
`dragMoveEvent` to call `acceptProposedAction()` whenever
`dragEnterEvent` already accepts the drag (i.e. the MIME data carries
`EMMM_MOD_MIME_TYPE`). This keeps Qt's interpreted cursor on the move/copy
shape across the target's area between `dragEnterEvent` and `dropEvent` instead
of reverting to the default arrow.

#### Scenario: Moving across an accepted mod card keeps the move cursor

- **WHEN** the user drags an internal mod card over another
  `FolderGridItemWidget` whose `dragEnterEvent` would accept it
- **THEN** `dragMoveEvent` SHALL call `acceptProposedAction()`
- **AND** the cursor SHALL remain the move cursor for the entire time the
  cursor is over that widget

#### Scenario: Moving across an accepted character row keeps the move cursor

- **WHEN** the user drags an internal mod card over an
  `ObjectListItemWidget` whose `dragEnterEvent` would accept it
- **THEN** `dragMoveEvent` SHALL call `acceptProposedAction()`
- **AND** the cursor SHALL remain the move cursor for the entire time the
  cursor is over that widget

#### Scenario: Non-internal MIME data is still ignored by mod cards

- **WHEN** the user drags external data whose MIME type is not
  `EMMM_MOD_MIME_TYPE` over a `FolderGridItemWidget`
- **THEN** `dragMoveEvent` SHALL defer to the superclass
  `dragMoveEvent` (which the panel's external-file import path relies on)
- **AND** SHALL NOT call `acceptProposedAction()` for the internal path