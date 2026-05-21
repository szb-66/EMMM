# Services Layer

Services encapsulate all business logic and I/O. They are instantiated in `main.py`'s composition root and injected into ViewModels.

## ConfigService

[app/services/config_service.py](app/services/config_service.py)

**Responsibility:** Read/write `config.json` in the application root directory.

| Method | Description |
|--------|-------------|
| `load_config()` | Loads + validates entire config; returns `AppConfig` (never raises — falls back to defaults) |
| `save_config(config)` | Full serialization of `AppConfig` to JSON |
| `save_setting(key, value, section)` | Single-key atomic update (read-modify-write) |

**Error handling:** `ConfigSaveError` (custom `IOError` subclass) on write failures.

## GameService

[app/services/game_service.py](app/services/game_service.py)

**Responsibility:** Detect XXMI Launcher structure and propose game entries.

| Method | Description |
|--------|-------------|
| `propose_games_from_path(path)` | Multi-layered detection: check launcher root → check path ancestry for known game folders → fallback single-game proposal |

**DetectionResult** dataclass: `is_detected`, `proposals: list[dict]`, `suggested_launcher_path`.

Known game folder keys: `{"GIMI", "SRMI", "WWMI"}` (from `constants.py`).

## ModService

[app/services/mod_service.py](app/services/mod_service.py)

**Responsibility:** All atomic filesystem + JSON operations for individual mod items.

### Loading
| Method | Description |
|--------|-------------|
| `get_item_skeletons(path, context)` | Scan directory → return skeleton models (name parsed via `_parse_folder_name`, ID via SHA1 of relative path) |
| `hydrate_item(skeleton, game_name, context)` | Read `properties.json` or `info.json` → return hydrated model. Includes "reality check" logic that syncs physical files with JSON metadata |

### Mutation
| Method | Description |
|--------|-------------|
| `toggle_status(item, target_status)` | Rename folder (add/remove `DISABLED` prefix). Handles persistence snapshot/restore. |
| `toggle_pin_status(item)` | Rename folder (add/remove `_pin` suffix) + update JSON |
| `rename_item(item, new_name)` | Rename folder + rewrite JSON (read-before-rename pattern to avoid file locks) |
| `delete_item(item)` | Move to recycle bin via `SystemUtils` |
| `convert_object_type(item_id, path, new_type)` | Update `object_type` in `properties.json` |

### Metadata
| Method | Description |
|--------|-------------|
| `update_item_properties(item, data)` | Merge dict into `info.json` and return updated `FolderItem` |
| `update_object_properties_from_db(item, db_data)` | Merge DB data into `properties.json`, copy thumbnail |
| `update_object(item, update_data)` | Handle rename (optional) + full metadata + thumbnail update |

### Image management
| Method | Description |
|--------|-------------|
| `add_preview_image(item, image_data)` | Save compressed image → update `info.json` |
| `remove_preview_image(item, path)` | Recycle bin single image → update metadata |
| `remove_all_preview_images(item)` | Recycle bin all images → clear metadata list |

### Creation
| Method | Description |
|--------|-------------|
| `analyze_source_path(path)` | Quick check if path is valid folder/archive, detect `.ini` presence |
| `create_mod_from_source(source, output_name, parent, cancel_flag)` | Copy folder or extract archive → write skeleton `info.json`. Supports smart extraction (unwrap single-root archives). Password-protected archives detected. |
| `create_manual_object(parent, data)` | Create folder + write `properties.json` + process thumbnail (Path/PIL/QImage sources) |

## DatabaseService

[app/services/database_service.py](app/services/database_service.py)

**Responsibility:** Load, cache, and query game object reference data from `schema.json`.

| Method | Description |
|--------|-------------|
| `get_all_game_types()` | Available game keys from schema |
| `get_schema_for_game(game_type)` | Per-game schema definition (rarity, element, weapon lists, aliases) |
| `get_all_objects_for_game(game_type)` | Load + combine all object data files linked in schema's `object_link` |
| `get_metadata_for_object(game_type, name)` | Case-insensitive lookup for single object |
| `find_best_object_match(db_objects, item_name)` | SequenceMatcher score + tag boost. Returns match dict with score. |
| `get_alias_for_game(game_type, key)` | Display-name alias from schema's `alias` section |
| `get_game_type_from_path(game_path)` | Infer game type by checking path parts against known game keys |

## ThumbnailService

[app/services/thumbnail_service.py](app/services/thumbnail_service.py)

**Responsibility:** Two-tier thumbnail caching + background generation.

- **L1 (memory):** `OrderedDict` with 100-item LRU eviction
- **L2 (disk):** JPEG files in `cache/thumbnails/`
- **Processing:** Pillow-based resize to 256×256, JPEG quality 85, progressive encoding
- **Dedicated thread pool:** 2 threads for image processing
- **Cache cleanup:** Age-based (>30 days) + size-based (>200MB) pruning

| Method | Description |
|--------|-------------|
| `get_thumbnail(item_id, source_path, default_type)` | Check L1 → L2 → return default + queue background generation |
| `invalidate_cache(item_id, path)` | Remove from both L1 and L2 |
| `cleanup_disk_cache(max_age_days, max_size_mb)` | Age + size pruning |

## IniKeyParsingService

[app/services/Iniparsing_service.py](app/services/Iniparsing_service.py)

**Responsibility:** Parse and save 3DMigoto `.ini` keybinding files.

- `load_keybindings_async(folder_path, game_root)` — async entry point (the only `asyncio`-based method in the app)
- `save_ini_changes(editable_keybindings)` — write changes back to `.ini` files

Files parsed: `d3dx.ini` (main), `d3dx_user.ini` (user overrides, paths relativized).

Keybinding model: `KeyBinding` dataclass with `keys`, `backs`, `assignments` (variable/value pairs), `type` (key/cycling/custom), and metadata (`ini_path`, `section`, `line_no`).

## WorkflowService

[app/services/workflow_service.py](app/services/workflow_service.py)

**Responsibility:** Orchestrate multi-step, transactional, or multi-item workflows.

| Method | Description |
|--------|-------------|
| `execute_exclusive_activation(plan)` | "Enable Only This" — disable all others, enable target, with rollback on failure |
| `reconcile_objects_with_database(game_path, game_type, local_items, db_objects)` | Match local↔DB objects → create missing + update existing |
| `reconcile_single_game(game)` | Self-contained reconciliation (fetches data itself) |
| `execute_object_creation(tasks, parent, progress_callback)` | Batch create multiple objects |
| `execute_creation_workflow(tasks, parent, cancel_flag)` | Batch create mods from sources, cancellable |
| `analyze_creation_sources(paths)` | Background analysis of dropped files (folders/archives) |

**Stubs** (not yet implemented): `apply_safe_mode`, `apply_preset`, `apply_randomize`, `apply_global_randomize`, `rename_preset`, `delete_preset`.

## FileWatcherService

[app/services/file_watcher_service.py](app/services/file_watcher_service.py)

**Responsibility:** Watch directories for external filesystem changes and notify via Qt signals.

- Uses `watchdog.Observer` with non-recursive watches
- Maps string keys (`"objectlist"`, `"foldergrid"`) to watched paths
- Filters out `opened`/`closed` events
- Supports suppression tokens for internal-change filtering
- `directory_changed` signal: `(key: str, changed_path: Path)`

## PersistUtils

[app/services/persist_utils.py](app/services/persist_utils.py)

Shared helpers used by both `ModService` and `IniKeyParsingService`:

- `find_game_root_from_folder(path)` — walk up from a mod folder to find the game root (where `d3dx_user.ini` lives)
- `read_user_persist_values(path)` — parse `d3dx_user.ini` for `$persist` keys
- `write_user_persist_values(path, values)` — write `$persist` key-value pairs
- `normalize_persist_key(key)` — normalize path separators in persist keys
- `strip_disabled_prefix(name)` — remove `DISABLED ` prefix from folder names
