## ADDED Requirements

### Requirement: Folder grid page switches are instant

`FolderGridPanel` SHALL display its content stack (placeholder, scroll area, empty state, shimmer) without any pop-up or slide animation on page switch. The stack SHALL switch to the target widget synchronously when `setCurrentWidget` is called.

#### Scenario: Navigating into a navigable folder shows the grid with no slide

- **WHEN** the user double-clicks a navigable folder and `items_updated` fires
- **THEN** the panel's content stack SHALL switch from the shimmer/placeholder widget to the scroll area widget with no vertical slide animation
- **AND** the grid SHALL be visible in its final position on the first paint after the switch

#### Scenario: Empty state appears with no slide

- **WHEN** a navigation or filter yields no items and `empty_state_changed` fires
- **THEN** the panel's content stack SHALL switch to the empty-state widget with no pop-up animation
- **AND** no `QPropertyAnimation` SHALL be running on the stack or its children as a result of the switch

### Requirement: Description editor pastes plain text only

`PreviewPanel`'s description editor SHALL accept plain text only. Pasted content SHALL NOT carry inline HTML styles (color, font, weight) from the source. Pasted text SHALL inherit the editor's theme color so it remains legible on the current theme background.

#### Scenario: Pasting rich-text content strips styling

- **WHEN** the user pastes content copied from a rich-text source (e.g. a web page with colored text) into the description editor
- **THEN** only the plain-text representation SHALL be inserted
- **AND** the inserted text SHALL render in the editor's theme color (not the source's inline color)
- **AND** the inserted text SHALL be legible against the editor's background on both light and dark themes

#### Scenario: Manually typed text remains unchanged

- **WHEN** the user types into the description editor without pasting
- **THEN** the editor SHALL behave exactly as before (no styling, theme-colored text)

### Requirement: INI config field labels wrap on overflow

`KeyBindingWidget`'s field-row label SHALL word-wrap when its text exceeds the row width available to the label. The label and its field SHALL share the row via a fixed stretch ratio so a long label wraps onto extra lines instead of pushing the field off the right edge of the panel. The field SHALL remain fully visible within its allotted width.

#### Scenario: Long variable name wraps instead of squeezing the field

- **WHEN** a keybinding's variable or section name is long enough that the label would otherwise exceed its natural row share
- **THEN** the label SHALL wrap onto additional lines
- **AND** the field SHALL remain visible within its stretch share of the row
- **AND** no horizontal scrolling SHALL be required to see or edit the field

#### Scenario: Short label stays on a single line

- **WHEN** a keybinding's variable or section name is short enough to fit on one line within its stretch share
- **THEN** the label SHALL NOT wrap and SHALL sit on a single line adjacent to its field

### Requirement: Settings dialog visible page matches highlighted tab on open

When `SettingsDialog` opens, the visible page of its content stack SHALL match the Pivot's initially highlighted tab. The user SHALL NOT see a tab/content mismatch on first display.

#### Scenario: Opening settings shows Mod Paths content under the Mod Paths tab

- **WHEN** the Settings dialog is constructed and shown
- **THEN** the Pivot SHALL highlight the "Mod Paths" (`games_tab`) route
- **AND** the content stack SHALL display the `games_tab` page (not the General page)
- **AND** no tab click SHALL be required to bring the visible page in sync with the highlight

## MODIFIED Requirements

### Requirement: Drag source shows a custom pixmap and stable move cursor

`FolderGridItemWidget.mouseMoveEvent` SHALL set a custom drag pixmap on the
`QDrag` constructed from the dragged mod's first preview thumbnail, capped to
a sane size on the long edge, with the hotspot centered. The drag pixmap SHALL
be rendered at approximately 50% opacity so underlying content remains visible
through the thumbnail during the drag. When the mod has no usable preview
thumbnail, it SHALL fall back to a `self.grab()` snapshot of the card rendered
at the same opacity. The drag source SHALL install a `DragMoveCursor` override
on `QApplication` for the duration of `drag.exec(...)` and SHALL restore the
previous cursor afterwards, including on exception, so the cursor reflects the
drag on every region of the application rather than reverting to the default
arrow.

#### Scenario: Dragging a mod with thumbnails shows its thumbnail as the pixmap

- **WHEN** the user starts dragging a mod card whose `preview_images` contains
  at least one image
- **THEN** `QDrag.setPixmap` SHALL be called with a `QPixmap` built from that
  image
- **AND** the pixmap SHALL be composited at approximately 50% opacity so the
  cursor can see underlying content
- **AND** `QDrag.setHotSpot` SHALL center the pixmap under the cursor
- **AND** the application cursor SHALL be the move cursor for the whole drag

#### Scenario: Dragging a mod without thumbnails falls back to the card snapshot

- **WHEN** the user starts dragging a mod card whose `preview_images` is empty
  or unreadable
- **THEN** `QDrag.setPixmap` SHALL be called with a `QPixmap` produced by
  `self.grab()` composited at approximately 50% opacity
- **AND** the drag SHALL otherwise behave identically

#### Scenario: Override cursor is always restored

- **WHEN** `drag.exec(...)` returns normally or raises
- **THEN** `QApplication.restoreOverrideCursor()` SHALL have been called
- **AND** the application cursor SHALL be back to its pre-drag shape