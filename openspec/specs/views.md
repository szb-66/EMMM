# Views

All views are PyQt6 widgets styled with `qfluentwidgets`. They follow a passive-view pattern — they observe ViewModel signals and forward user actions to ViewModel slots.

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
- `PopUpAniStackedWidget` — switches between placeholder, scroll area, empty state, and shimmer
- Drag & drop enabled via `dragEnterEvent`/`dropEvent`

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
