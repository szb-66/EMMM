# ViewModels

ViewModels manage panel state, coordinate data flow between Views and Services, and emit signals for UI updates. All I/O-bound work is dispatched to `QThreadPool` via `Worker`.

## MainWindowViewModel

[app/viewmodels/main_window_vm.py](app/viewmodels/main_window_vm.py)

**Role:** Top-level orchestrator. Owns `active_game`, `active_object`, the global config reference, and the `FileWatcherService` instance. Routes signals between child ViewModels.

### Signals
| Signal | Payload | Description |
|--------|---------|-------------|
| `toast_requested` | `str, ToastLevel` | Global notification |
| `global_operation_started` | `str` | Lock UI, show spinner |
| `global_operation_finished` | — | Unlock UI |
| `game_list_updated` | `list[dict]` | Refresh game combo |
| `active_game_changed` | `object` | Game switch |
| `category_switch_requested` | `str` | Switch sidebar filter |
| `play_button_state_changed` | `bool` | Enable/disable play button |

### Key methods
| Method | Trigger | Behavior |
|--------|---------|----------|
| `start_initial_load()` | App start | Async load config via Worker |
| `set_current_game(game)` | Game selection | Save preference → clear old state → load objectlist → start file watcher |
| `set_active_object(data)` | Object selection | Find model by ID → load foldergrid → start file watcher |
| `request_main_refresh()` | Refresh button | Re-scan current game's objectlist |
| `on_category_selected(key)` | Sidebar click | Set category filter on objectlist VM |

### Domino effects
- `_on_active_object_modified`: Object toggled → refresh foldergrid
- `_on_active_object_deleted`: Object deleted → clear foldergrid + preview
- `_on_foldergrid_item_modified`: Mod toggled → update preview if it's the current item
- `_on_objectlist_refresh_complete`: After refresh → optionally restore foldergrid sub-path

### File watcher management
- Watches objectlist root dir (key: `"objectlist"`) and current object dir (key: `"foldergrid"`)
- Debounces changes (400ms) and supports suppression tokens for internal operations

## ModListViewModel (×2 instances)

[app/viewmodels/mod_list_vm.py](app/viewmodels/mod_list_vm.py)

**Role:** Manages the item list for either `CONTEXT_OBJECTLIST` or `CONTEXT_FOLDERGRID`. Handles loading, filtering, searching, sorting, and single-item operations.

### Context-dependent behavior
| Feature | OBJECTLIST | FOLDERGRID |
|---------|------------|------------|
| Item type | `ObjectItem` / `CharacterObjectItem` | `FolderItem` |
| Category filter | Character vs Other | N/A |
| Detail filters | rarity, element, gender, weapon | author, tags |
| Search scope | name, tags, element, weapon | name, tags, author, description |
| Empty state | "No Objects Found" | "Folder is Empty" |
| Navigation | N/A | Breadcrumb + subfolder |

### Key signals
| Signal | Description |
|--------|-------------|
| `items_updated` | Emits `list[dict]` + optional `item_id_to_select` |
| `item_needs_update` | Single-item refresh after hydration |
| `loading_started/finished` | Show/hide shimmer |
| `active_selection_changed` | Selection highlight |
| `active_object_modified` | Domino: notify MainWindowVM |
| `foldergrid_item_modified` | Domino: notify PreviewPanel |
| `active_object_deleted` | Domino: clear dependent views |

### Loading flow
1. `load_items(path, game, is_new_root)` → increment `current_load_token` (race-condition guard) → emit `loading_started` → start Worker for `get_item_skeletons`
2. `_on_skeletons_loaded` → set `master_list` → `_update_available_filters` → `apply_filters_and_search` → emit `items_updated` + `load_completed`
3. Lazy hydration: `request_item_hydration(item_id)` → Worker → `_on_item_hydrated` → `item_needs_update`

### Filtering and search
- Category filter (objectlist only): `active_category_filter` splits Character vs Other
- Detail filters: `active_filters` dict applied as attribute matches
- Search: `on_search_query_changed` (debounced 300ms) → relevance scoring
- Sort: score → is_pinned → is_enabled → name

### Item operations
All follow the same pattern: guard (`_processing_ids` check) → Worker → result slot → state update → signal:
- `toggle_item_status`, `toggle_pin_status`, `rename_item`, `delete_item`
- `convert_object_type`, `update_object_item`, `initiate_sync_for_item`

### Reconciliation
- `get_reconciliation_preview()`: Dry-run match counts without executing
- `initiate_reconciliation()`: Full sync — create missing + update existing via `WorkflowService`

## PreviewPanelViewModel

[app/viewmodels/preview_panel_vm.py](app/viewmodels/preview_panel_vm.py)

**Role:** Manages the right-side detail panel for the selected mod.

### State tracking
- `current_item_model: FolderItem | None`
- `is_description_dirty`, `is_ini_dirty` — edit-state flags
- `_unsaved_description`, `_unsaved_ini_changes` — pending edits
- `editable_keybindings: list[KeyBinding]` — live .ini editor state

### Key methods
| Method | Description |
|--------|-------------|
| `set_current_item(data)` | Load item + start async .ini parsing. Guards unsaved changes. |
| `save_description()` | Worker → update description via `ModService.update_item_properties` |
| `save_ini_config()` | Worker → save via `IniKeyParsingService.save_ini_changes` |
| `on_description_changed(text)` | Track live description edits |
| `on_keybinding_edited(...)` | Track live .ini edits |
| `add_new_thumbnail(image_data)` | Worker → add preview image |
| `remove_thumbnail(path)` | Worker → remove single image |
| `remove_all_thumbnails()` | Worker → clear all images |
| `paste_thumbnail_from_clipboard()` | Get clipboard image via `ImageUtils` → add |
| `toggle_current_item_status(enabled)` | Toggle mod enabled/disabled |
| `clear_panel()` | Reset state → show null state in view |

### Unsaved changes guard
When the user navigates away with dirty state:
1. `set_current_item` detects `is_description_dirty`
2. Emits `unsaved_changes_prompt_requested` with next-item context
3. View shows dialog → calls `discard_changes_and_proceed` or cancels navigation

### .ini editing data model
- `KeyBinding` objects contain mutable `keys` (list), `backs` (list), and `Assignment` objects (variable/value)
- `_unsaved_ini_changes` tracks per-binding changes by `binding_id`
- `save_ini_changes` persists all modified bindings via the parsing service

## SettingsViewModel

[app/viewmodels/settings_vm.py](app/viewmodels/settings_vm.py)

**Role:** Transactional dialog state manager. Operates on a temporary copy of config — only persists to disk when user clicks Save.

### Transactional state
- `original_config: AppConfig | None` — snapshot loaded when dialog opens
- `temp_games: list[Game]` — mutable game list for editing
- `temp_launcher_path`, `temp_auto_play` — mutable launcher settings

### Key methods
| Method | Description |
|--------|-------------|
| `load_current_config(config)` | Initialize temp state from config |
| `save_all_changes()` | Validate (unique names) → write via `ConfigService` → emit `config_updated` |
| `add_game_from_path(path)` | XXMI detection → propose games → request confirmation |
| `add_games_to_list(proposals)` | Add fully-specified games to temp list |
| `process_individual_proposals(proposals)` | Route complete proposals directly, request game_type for incomplete ones |
| `set_game_type_and_add(proposal, game_type)` | Finalize + add game with user-selected type |
| `update_temp_game(id, name, path, type)` | Edit existing game in temp list |
| `remove_temp_game(id)` | Remove from temp list |

### Reconciliation in settings
`initiate_reconciliation_for_game(game_id)` — triggers background sync per game from the settings dialog.
