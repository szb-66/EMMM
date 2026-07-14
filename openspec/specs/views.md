# Views

All views are PyQt6 widgets styled with `qfluentwidgets`. They follow a passive-view pattern — they observe ViewModel signals and forward user actions to ViewModel slots. All user-facing strings use `i18n.tr(key, **fmt)` for multi-language support.

## MainWindow

[app/views/main_window.py](app/views/main_window.py)

**Role:** Application shell using `FluentWindow` (qfluentwidgets). Composed of header bar + sidebar navigation + splitter with three panels.

### Layout structure
```
FluentWindow
├── NavigationInterface (sidebar)
│   ├── "Main Content" (hidden)
│   ├── separator
│   ├── "Character" → on_category_selected('character')
│   └── "Other" → on_category_selected('other')
└── central widget (QWidget)
    ├── Header bar (QHBoxLayout)
    │   ├── Left: Game combo, Safe Mode switch (hidden)
    │   └── Right: Refresh, Settings, Play buttons
    ├── Separator (QFrame.HLine)
    └── QSplitter (horizontal)
        ├── ObjectListPanel (min 284px, max 400px)
        ├── FolderGridPanel (stretch 1)
        └── PreviewPanel (min 276px)
```

### Signal wiring
- `gamelist_combo.currentIndexChanged` → `main_window_vm.set_current_game_by_name`
- `refresh_button.clicked` → `main_window_vm.request_main_refresh`
- `play_button.clicked` → `main_window_vm.on_play_button_clicked`
- `object_list_panel.item_selected` → `main_window_vm.set_active_object`
- `folder_grid_panel.item_selected` → `preview_panel_vm.set_current_item`

### Toast notifications
All VM toast signals are connected to `_on_toast_requested` which creates `InfoBar` at `BOTTOM_RIGHT`:
- `success` → green, 2000ms
- `warning` → orange, 3000ms
- `error` → red, 4000ms
- `info` → blue, 2000ms

### Bulk operation overlay
- `_on_bulk_operation_started`: Disable all panels, show progress `InfoBar`
- `_on_bulk_operation_finished`: Re-enable, close progress, refresh, show errors

## ObjectListPanel

[app/views/sections/objectlist_panel.py](app/views/sections/objectlist_panel.py)

**Role:** Left panel showing game objects (characters/weapons/etc.) as a list.

### Components
- `SearchLineEdit` — search bar
- `DropDownToolButton` (Filter) — filter by tags, rarity, element, etc.
- `ListView`-based item list with custom `ObjectListItemWidget` items

### Key signals
- `item_selected(object)` → forwarded to `MainWindowViewModel.set_active_object`

### Context menu actions
- Edit object, Delete, Open in Explorer, Convert type, Sync with DB

## FolderGridPanel

[app/views/sections/foldergrid_panel.py](app/views/sections/foldergrid_panel.py)

**Role:** Center panel showing mods in a flow/grid layout with breadcrumb navigation.

### Components
- `SearchLineEdit` — search mods
- `DropDownToolButton` (Filter) — dynamic filter controls (author, tags)
- `BreadcrumbWidget` — hierarchical path navigation
- `FlowGridWidget` (ScrollArea) — grid of `FolderGridItemWidget` cards
- `PrimaryDropDownPushButton` (Create Mod) — add from archives or folder
- `QStackedWidget` — switches between placeholder, scroll area, empty state, and shimmer
- Drag & drop: `FolderGridPanel` accepts external OS file/folder drops for mod import via `dragEnterEvent`/`dropEvent`
- Context menu (right-click empty area): "New Folder..." for creating navigable folders

### Drag-and-drop (internal)
- `FolderGridItemWidget` is both drag source and drop target
- Drag source: initiates `QDrag` with `EMMM_MOD_MIME_TYPE` carrying the mod's ID
- Drop on folder: moves mod into that folder
- Drop on another mod: prompts auto-group dialog
- `ObjectListItemWidget` accepts drops from foldergrid (`dragEnterEvent`/`dropEvent`) → emits `move_to_character_requested`
- `ThumbnailWidget` accepts image file drops from OS to add preview images

### Key signals
- `item_selected(object)` → forwarded to `PreviewPanelViewModel.set_current_item`

### Filter controls
Dynamic UI generated from `available_filters_changed` signal:
- Tags: `FlowLayout` with `CheckBox` widgets (multi-select)
- Author: `ComboBox` with "All" + unique authors (single-select)
- Apply/Reset buttons

### Creation flow
1. User drops files/clicks "Create Mod" → paths sent to VM
2. VM starts background analysis → `creation_tasks_prepared` signal
3. Panel shows `ConfirmationListDialog` for name/task review
4. User confirms → `ProgressDialog` + `start_background_creation`
5. On completion: summary toast, optional `FailureReportDialog`

### Exclusive activation
"Enable Only This" triggers confirmation `MessageBox` listing mods to be disabled → VM `proceed_with_exclusive_activation`.

### Requirement: List panels reuse existing widgets on update

When `items_updated` fires, `FoldergridPanel` and `ObjectlistPanel` SHALL reuse existing child widgets for items whose IDs appear in both the old and new lists. Widgets SHALL be destroyed only for removed items, and created only for added items. The panel SHALL NOT appear blank between updates.

#### Scenario: Sort reorder reuses all widgets

- **WHEN** `items_updated` emits a list containing the same item IDs in a different order
- **THEN** no widgets SHALL be destroyed or created
- **AND** existing widgets SHALL be repositioned to match the new order

## PreviewPanel

[app/views/sections/preview_panel.py](app/views/sections/preview_panel.py)

**Role:** Right panel showing detailed mod information and providing editing capabilities.

### Sections
- **Header:** Mod name, enable/disable toggle, safe mode tag
- **Thumbnail area:** Preview images with add/remove/clear controls + clipboard paste
- **Description editor:** Multi-line text editor with save indicator
- **Metadata display:** Author, tags
- **.ini config editor:** Keybinding list with inline editing

### Unsaved changes dialog
On navigation away with dirty state, the ViewModel emits `unsaved_changes_prompt_requested`. Panel shows a confirmation dialog. User choice routes to `discard_changes_and_proceed` or cancels navigation.

## Dialogs

| Dialog | Purpose |
|--------|---------|
| `SettingsDialog` | Multi-tab: Games (add/edit/remove/sync), Launcher, Presets (stub) |
| `EditGameDialog` | Edit game name/path/type; supports force-selection mode for unconfigured games |
| `EditObjectDialog` | Edit object metadata + thumbnail |
| `CreateObjectDialog` | Manual object creation with fields depending on type (Character vs Other) |
| `SelectGameTypeDialog` | Pick game type when XXMI detection can't deduce it |
| `RenameDialog` | Simple name-input dialog |
| `PasswordDialog` | Archive decryption password input |
| `ProgressDialog` | Cancellable progress bar for background operations |
| `ConfirmationListDialog` | Review creation tasks before executing |
| `SyncSelectionDialog` | Manual DB match selection when auto-match confidence is low |
| `FailureReportDialog` | List of failed operations with reason |
| `ConfirmationListDialog` | Yes/No confirmation with list display |

## Widgets

| Widget | Description |
|--------|-------------|
| `BreadcrumbWidget` | Clickable path segments for folder navigation |
| `FlowGridWidget` | `FlowLayout`-based scrollable grid container |
| `FolderGridItemWidget` | Mod card: thumbnail, name, status indicator, action buttons |
| `ObjectListItemWidget` | Object list item: icon, name, pin/status |
| `ThumbnailWidget` | Clickable thumbnail with selection overlay |
| `SyncCandidateWidget` | DB match candidate display with thumbnail |
| `CreationTaskWidget` | Creation task summary card |
| `ProgressFlyout` | Flyout-based progress indicator |
| `KeybindingWidget` | Inline .ini keybinding editor (key/back/assignment) |
| `IniFileGroupWidget` | Grouped .ini file display |
| `ShimmerFrame` | Loading skeleton shimmer animation |

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

#### Scenario: Non-internal MIME data is still ignored by mod cards

- **WHEN** the user drags external data whose MIME type is not
  `EMMM_MOD_MIME_TYPE` over a `FolderGridItemWidget`
- **THEN** `dragMoveEvent` SHALL defer to the superclass
  `dragMoveEvent` (which the panel's external-file import path relies on)
- **AND** SHALL NOT call `acceptProposedAction()` for the internal path
