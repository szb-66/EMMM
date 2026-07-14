# Data Models

All model classes are immutable `frozen=True` dataclasses. No instance is ever mutated — changes produce a new instance via `dataclasses.replace()`.

## Game

[app/models/game_model.py](app/models/game_model.py)

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | UUID4, auto-generated |
| `name` | `str` | User-facing display name |
| `path` | `Path` | Mods directory (validated as existing dir in `__post_init__`) |
| `game_type` | `str \| None` | DB lookup key (e.g. `"GIMI"`, `"SRMI"`) |

## AppConfig

[app/models/config_model.py](app/models/config_model.py)

| Field | Type | Description |
|-------|------|-------------|
| `games` | `list[Game]` | Configured games |
| `last_active_game_id` | `str \| None` | Restored on next launch |
| `last_active_object_id` | `str \| None` | Reserved |
| `last_active_folder_id` | `str \| None` | Reserved |
| `safe_mode_enabled` | `bool` | Global safe mode |
| `presets` | `dict[str, Preset]` | Named mod presets |
| `launcher_path` | `str \| None` | Path to XXMI Launcher.exe |
| `auto_play_on_startup` | `bool` | Auto-launch game |
| `window_geometry` | `tuple[int,int,int,int] \| None` | Restored window position |
| `splitter_sizes` | `tuple[int,int,int] \| None` | Restored splitter layout |
| `description_editor_height` | `int \| None` | Preview panel editor height |
| `object_list_view_mode` | `str` | `"list"` or `"card"` |
| `language` | `str` | UI language code, default `"zh"` |

## BaseModItem

[app/models/mod_item_model.py](app/models/mod_item_model.py)

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | SHA1 of relative path from parent scan dir |
| `actual_name` | `str` | Display name (stripped of DISABLED prefix and _pin suffix) |
| `folder_path` | `Path` | Absolute filesystem path |
| `status` | `ModStatus` | `ENABLED` / `DISABLED` |
| `is_pinned` | `bool` | Whether item is pinned to top |
| `is_skeleton` | `bool` | `True` until hydrated with full metadata |

### ObjectItem (extends BaseModItem)

Used in objectlist context. Represents a character or category folder.

| Field | Type | Description |
|-------|------|-------------|
| `object_type` | `ModType \| None` | `CHARACTER`, `WEAPON`, `UI`, `OTHER` |
| `tags` | `list[str]` | Searchable tags |
| `release_date` | `date \| None` | Character release date |
| `thumbnail_path` | `Path \| None` | Path to thumbnail image |

#### CharacterObjectItem (extends ObjectItem)

| Field | Type |
|-------|------|
| `gender` | `str \| None` |
| `rarity` | `str \| None` |
| `element` | `str \| None` |
| `weapon` | `str \| None` |
| `region` | `str \| None` |

#### GenericObjectItem (extends ObjectItem)

| Field | Type |
|-------|------|
| `subtype` | `str \| None` |

### FolderItem (extends BaseModItem)

Used in foldergrid context. Represents a single mod or navigable subfolder.

| Field | Type | Description |
|-------|------|-------------|
| `author` | `str \| None` | Mod author |
| `description` | `str \| None` | Mod description |
| `tags` | `list[str]` | Searchable/filterable tags |
| `preview_images` | `list[Path]` | Screenshot image paths |
| `is_navigable` | `bool \| None` | `True` = subfolder, `False`/`None` = leaf mod |
| `is_safe` | `bool` | Safe mode tag |
| `last_status_active` | `bool` | Previous enabled state (for restore) |
| `preset_name` | `str \| None` | Associated preset name |

## Persistence strategy

### Folder naming convention

- **Disabled:** `DISABLED_<actual_name>[<optional text>]` (regex prefix, case-insensitive)
- **Pinned:** `<actual_name>_pin` (suffix, case-sensitive)
- Both can combine: `DISABLED_MyMod_pin`

### Metadata files

- **Objectlist items:** `properties.json` — stores `object_type`, `thumbnail_path`, `tags`, `rarity`, `element`, `gender`, `weapon`, `region`, `subtype`, `is_pinned`, `persistent_state_snapshot`
- **Foldergrid items:** `info.json` — stores `actual_name`, `author`, `description`, `tags`, `image_paths`, `is_safe`, `is_pinned`, `preset_name`, `persistent_state_snapshot`
- **Global config:** `config.json` (project root) — stores settings, games, UI prefs, presets
- **Game databases:** `app/assets/schema.json` + linked JSON files — object reference data per game type

### d3dx_user.ini persistence snapshot

When a mod is disabled, its `persist` key-value pairs (matching `$<relative_path>\`) are snapshotted into the metadata JSON. On re-enable, they are restored to `d3dx_user.ini`. This preserves per-mod runtime state (e.g., $dress values) across disable/enable cycles.
