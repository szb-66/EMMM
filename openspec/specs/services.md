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

[app/services/mod_service/](app/services/mod_service/) — package with 5 mixins + composition root

**Responsibility:** All atomic filesystem + JSON operations for individual mod items.

After ADR 0001 (large-file modularization), `ModService` was split from a monolithic `mod_service.py` into a package with mixin classes and a thin composition root (`service.py`):

| File | Mixin | Responsibilities |
|------|-------|-----------------|
| `_load_mixin.py` | `_LoadMixin` | Directory scanning, skeleton loading, lazy hydration, archive probing, reality-check logic |
| `_toggle_mixin.py` | `_ToggleMixin` | Enable/disable with persist snapshot/restore |
| `_crud_mixin.py` | `_CrudMixin` | Rename, delete, pin toggle, move, folder creation, auto-grouping, object conversion |
| `_preview_mixin.py` | `_PreviewMixin` | Preview image add/remove/reorder, metadata JSON read/write |
| `_creation_mixin.py` | `_CreationMixin` | Source analysis, archive extraction, manual object creation, mod-from-source creation |
| `service.py` | `ModService` | Composition root inheriting all mixins; backwards-compat via `__init__.py` re-export |

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
| `move_item_to(item_id, source, target_dir)` | Move folder + recompute ID (from `_crud_mixin`) |
| `create_empty_folder(parent, name)` | Create empty navigable folder with encoded name (from `_crud_mixin`) |
| `auto_group_items(items, group_name, parent)` | Move multiple items into a new folder (from `_crud_mixin`) |

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
| `reorder_preview_images(item, image_paths)` | Reorder `preview_images` list in `info.json` + invalidate thumbnail cache (from `_preview_mixin`) |

### Loading (mixin)
| Method | Description |
|--------|-------------|
| `_parse_folder_name(name)` | Decode folder name to extract disabled prefix, pin suffix, and actual name |
| `_generate_stable_id(rel_path)` | SHA1-based stable ID for item dedup |
| `_scan_for_ini_files(folder)` | Recursively find `.ini` files in mod folder |
| `_probe_archive_for_ini(archive_path)` | Peek into ZIP archives for `.ini` files via `zipfile.ZipFile.namelist()` without extraction |
| `_reality_check(item, filesystem, json_meta)` | Sync physical file state with JSON metadata |

### Creation
| Method | Description |
|--------|-------------|
| `analyze_source_path(path)` | Quick check if path is valid folder/archive, detect `.ini` presence |
| `create_mod_from_source(source, output_name, parent, cancel_flag)` | Copy folder or extract archive → write skeleton `info.json`. Supports smart extraction (unwrap single-root archives). Password-protected archives detected. |
| `create_manual_object(parent, data)` | Create folder + write `properties.json` + process thumbnail (Path/PIL/QImage sources) |
| `create_foldergrid_item(parent, data)` | Create mod folder with name/pin state |
| `create_objectlist_item(parent, data)` | Create object folder with metadata |
| `_smart_extract_archive(archive_path, dest, cancel_flag)` | Extract with single-root unwrap detection |
| `_encode_folder_name(name, enabled, pinned)` | Encode name with DISABLED prefix and/or _pin suffix |
| `_compute_item_id(parent, name)` | Recompute stable ID after folder rename/move |

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
| `invalidate_cache(item_id, path)` | Remove from both L1 and L2 caches. L2 cache file is always keyed by `item_id` regardless of `path` parameter. |
| `cleanup_disk_cache(max_age_days, max_size_mb)` | Age + size pruning |

### Requirement: Cache invalidation clears both L1 and L2 caches
The system SHALL remove cached thumbnails from both L1 (memory) and L2 (disk) caches when invalidated. The L2 cache file is always identified by `item_id`, never by source image path.

#### Scenario: Invalidate cache clears disk cache by item_id
- **WHEN** `invalidate_cache(item_id="mod_123")` is called
- **THEN** the L1 cache for `mod_123` SHALL be cleared
- **AND** the L2 cache file `cache/thumbnails/mod_123.jpg` SHALL be deleted

#### Scenario: Invalidate cache works regardless of path parameter
- **WHEN** `invalidate_cache(item_id="mod_123", path=some_source_path)` is called (e.g., from thumbnail deletion flow)
- **THEN** the L2 cache file `cache/thumbnails/mod_123.jpg` SHALL still be deleted
- **AND** the `path` parameter SHALL NOT prevent L2 cache deletion

#### Scenario: Thumbnail regenerates after cache invalidation
- **WHEN** the grid thumbnail is requested after cache invalidation and the first `preview_images` entry has changed
- **THEN** a new thumbnail SHALL be generated from the updated `preview_images[0]`
- **AND** the foldergrid SHALL display the new thumbnail

## IniKeyParsingService

[app/services/Iniparsing_service.py](app/services/Iniparsing_service.py)

**Responsibility:** Parse and save 3DMigoto `.ini` keybinding files.

- `load_keybindings_async(folder_path, game_root)` — async entry point (the only `asyncio`-based method in the app)
- `save_ini_changes(editable_keybindings)` — write changes back to `.ini` files and persist runtime state
- `sync_runtime_persist_to_source(folder_path, game_root)` — copy current runtime persist values from `d3dx_user.ini` into source `.ini` `global persist` defaults at disable time

Files parsed: `d3dx.ini` (main), `d3dx_user.ini` (user overrides, paths relativized).

Keybinding model: `KeyBinding` dataclass with `keys`, `backs`, `assignments` (variable/value pairs), `type` (key/cycling/custom), and metadata (`ini_path`, `section`, `line_no`).

### Persistence Requirements

#### Requirement: Disable-time runtime persist synchronization
When disabling a mod, `ModService` SHALL synchronize the mod's current runtime persist values from the corresponding game root `d3dx_user.ini` into the mod's own source `.ini` files before renaming the mod folder.

##### Scenario: Path-based persist value is written to source ini
- **WHEN** an enabled mod contains `global persist $swapvar = 0`, its source file maps to a path-based runtime key, and `d3dx_user.ini` contains that key with value `5`
- **THEN** disabling the mod updates the source `.ini` `global persist $swapvar` value to `5` before the folder is renamed

##### Scenario: Cycle options remain intact
- **WHEN** a persistent assignment has cycle options such as `$swapvar = 0,1,2,3,4,5`
- **THEN** disabling the mod updates only the `global persist` default and MUST NOT replace the cycle option list with the current value

##### Scenario: No runtime value leaves source ini unchanged
- **WHEN** a mod has persistent assignments but `d3dx_user.ini` does not contain matching runtime keys
- **THEN** disabling the mod does not change those source `.ini` defaults

#### Requirement: Namespace persist key ownership with cross-file resolution
Disable-time synchronization SHALL use parsed persistent assignments to determine which runtime keys belong to the target mod, including namespace-derived keys. The parsed persistent assignments SHALL be collected from ALL `.ini` files in the mod folder using a folder-wide `global persist` declaration map, not file-local declarations alone.

##### Scenario: Namespace persist value is written to source ini
- **WHEN** a mod `.ini` declares `namespace = my_namespace`, contains `global persist $swapvar = 0`, and `d3dx_user.ini` contains `$\my_namespace\swapvar = 2`
- **THEN** disabling the mod updates that source `.ini` `global persist $swapvar` value to `2`

##### Scenario: Namespace persist value from sibling file is written to source ini
- **WHEN** `SelectionMenu.ini` declares `namespace = JeanKnight` and `global persist $BodyA = 1`, and `Keys.ini` in the same folder contains `[KeyBodyAToggle]` with `$BodyA = 0,1`, and `d3dx_user.ini` contains `$\jeanknight\bodya = 0`
- **THEN** disabling the mod updates `SelectionMenu.ini`'s `global persist $BodyA` value to `0`

##### Scenario: Unowned runtime values are ignored
- **WHEN** `d3dx_user.ini` contains runtime keys that are not produced by parsing the target mod's persistent assignments
- **THEN** disabling the target mod MUST NOT write those unrelated runtime values into the target mod's source `.ini` files

#### Requirement: Snapshot restore remains available
Disable-time source synchronization SHALL NOT remove the existing metadata snapshot and re-enable restore behavior.

##### Scenario: Runtime file is cleared after disable
- **WHEN** a mod is disabled after runtime persist values are captured and `d3dx_user.ini` is later cleared
- **THEN** re-enabling the mod restores the captured values from metadata into `d3dx_user.ini`

##### Scenario: Source synchronization and snapshot use same runtime value
- **WHEN** disabling a mod captures a runtime value for a persistent assignment
- **THEN** the value written to the source `.ini` default and the value stored in `persistent_state_snapshot` represent the same current runtime state

#### Requirement: Source ini write safety
Disable-time source synchronization SHALL preserve existing `.ini` write safety behavior.

##### Scenario: Backup is created before modifying source ini
- **WHEN** disabling a mod requires changing a source `.ini` file and no backup exists
- **THEN** EMMM creates a one-time backup beside the source `.ini` before writing changes

##### Scenario: Source write failure is reported
- **WHEN** disabling a mod requires changing a source `.ini` file but the write fails
- **THEN** the disable operation reports failure rather than silently discarding the synchronization error

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

- Uses `watchdog.Observer` with recursive watches
- Maps string keys (`"objectlist"`, `"foldergrid"`) to watched paths
- Filters out `opened`/`closed` events, directory-creation events, and directory-modified events
- Supports `ignore_patterns` per-key to filter out internal metadata writes (e.g., `**/info.json`, `**/properties.json`)
- Supports suppression tokens for internal-change filtering; suppressed events are silently dropped
- `directory_changed` signal: `(key: str, changed_path: Path)`

### Requirement: FileWatcherService directory watching

`FileWatcherService` SHALL monitor directories using `watchdog.Observer` with recursive watches and emit `directory_changed(key, changed_path)` via Qt signals for filesystem events. When a watch key is suppressed via `suppress_watch(key, duration_ms)`, all events for that key SHALL be silently dropped for the suppression duration. No events SHALL be queued or replayed when suppression expires.

#### Scenario: Suppressed events are dropped silently

- **WHEN** a watch key has an active suppression token
- **AND** a filesystem event occurs in the watched directory
- **THEN** the event SHALL be dropped without queuing
- **AND** no `directory_changed` signal SHALL be emitted for the suppressed event after suppression expires

#### Scenario: Events after suppression expire are processed normally

- **WHEN** a watch key's suppression token expires
- **AND** a new filesystem event occurs in the watched directory
- **THEN** `directory_changed` SHALL be emitted normally for the new event

#### Scenario: Deleting nested subfolder triggers refresh

- **WHEN** a mod folder contains a subdirectory and the user deletes that subdirectory via Windows Explorer
- **THEN** FileWatcherService SHALL emit `directory_changed` with the key for the watched directory
- **AND** the UI SHALL refresh to reflect the deletion

### Requirement: ModService toggle status returns updated model

When a single item's status is toggled, `ModService` SHALL return the updated item model in the result dict under the `data` key. The caller SHALL update the item in its internal lists in-place without triggering a full directory re-scan.

#### Scenario: Toggling one mod returns complete model

- **WHEN** `toggle_status` succeeds for a single item
- **THEN** the result dict SHALL include a `data` key containing the updated `BaseModItem` model
- **AND** the model SHALL have the new `folder_path` and `status` fields

## PersistUtils

[app/services/persist_utils.py](app/services/persist_utils.py)

Shared helpers used by both `ModService` and `IniKeyParsingService`:

- `find_game_root_from_folder(path)` — walk up from a mod folder to find the game root (where `d3dx_user.ini` lives)
- `read_user_persist_values(path)` — parse `d3dx_user.ini` for `$persist` keys
- `write_user_persist_values(path, values)` — write `$persist` key-value pairs
- `normalize_persist_key(key)` — normalize path separators in persist keys
- `strip_disabled_prefix(name)` — remove `DISABLED ` prefix from folder names

## NoteService

[app/services/note_service.py](app/services/note_service.py)

**Responsibility:** Read/write per-mod keybinding notes persisted in `_emm_notes.json`.

| Method | Description |
|--------|-------------|
| `load_notes(mod_path)` | Read `_emm_notes.json` from mod directory; returns list of note dicts |
| `save_notes(mod_path, notes)` | Atomic write (tempfile + replace) notes to `_emm_notes.json` |

Notes format: list of `{"id": str, "content": str, "updated_at": str}` dicts.
