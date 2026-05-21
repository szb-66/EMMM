# Core Layer

## Constants

[app/core/constants.py](app/core/constants.py)

| Constant | Value | Purpose |
|----------|-------|---------|
| `APP_NAME` | `"EMM Manager"` | Application display name |
| `ORG_NAME` | `"reynalivan"` | Qt organization name |
| `APP_VERSION` | `"0.0.1"` | Current version |
| `DISABLED_PREFIX_PATTERN` | `re.compile(r"^(disabled)[\s_]+", re.I)` | Match `DISABLED_` or `disabled ` prefix in folder names |
| `PIN_SUFFIX` | `"_pin"` | Suffix for pinned folders |
| `CONFIG_FILE_NAME` | `"config.json"` | Global config file |
| `SCHEMA_FILE_NAME` | `"schema.json"` | Game reference database schema |
| `CACHE_DIR_NAME` | `"cache"` | Thumbnail cache directory |
| `LOG_DIR_NAME` | `"logs"` | Log output directory |
| `PROPERTIES_JSON_NAME` | `"properties.json"` | Objectlist item metadata |
| `INFO_JSON_NAME` | `"info.json"` | Foldergrid item metadata |
| `OBJECT_THUMBNAIL_SUFFIX` | `"_thumb"` | Object thumbnail filename suffix |
| `OBJECT_THUMBNAIL_EXACT` | `{"thumb", "folder"}` | Exact thumbnail filenames (no ext) |
| `FOLDER_PREVIEW_PREFIX` | `"preview"` | Preview image filename prefix |
| `SUPPORTED_IMAGE_EXTENSIONS` | `(".png", ".jpg", ".jpeg", ".webp")` | Accepted image formats |
| `DEBOUNCE_DELAY_MS` | `300` | Search debounce interval |
| `CONTEXT_OBJECTLIST` | `"objectlist"` | Objectlist VM context key |
| `CONTEXT_FOLDERGRID` | `"foldergrid"` | Foldergrid VM context key |
| `KNOW_XXMI_FOLDERS` | `{"GIMI", "SRMI", "WWMI"}` | Known game identifiers |

## GlobalSignals

[app/core/signals.py](app/core/signals.py)

Singleton `QObject` for application-wide signals that don't fit into the ViewModel hierarchy:

| Signal | Payload | Purpose |
|--------|---------|---------|
| `toast_requested` | `str, str` | Deep service → UI notification (message, level) |
| `log_message_requested` | `str, str` | Cross-component logging (level, message) |

Usage note: Most communication should use ViewModel-specific signals. `GlobalSignals` is for edge cases like a service needing to surface a toast without a ViewModel reference.

## Utils

### SystemUtils
[app/utils/system_utils.py](app/utils/system_utils.py)

- `open_path_in_explorer(path)` — open in OS file manager
- `move_to_recycle_bin(path)` — send2trash wrapper
- `generate_item_id(path, parent)` — SHA1-based stable ID
- `get_initial_name(name, length)` — avatar initial generation

### ImageUtils
[app/utils/image_utils.py](app/utils/image_utils.py)

- `find_next_available_preview_path(folder, base_name)` — generate sequential preview filenames
- `compress_and_save_image(source, target)` — resize + compress + save
- `get_image_from_clipboard()` — read clipboard as PIL/QImage

### AsyncUtils
[app/utils/async_utils.py](app/utils/async_utils.py)

- `Worker(signals, fn, *args, **kwargs)` — `QRunnable` subclass that runs `fn` in a thread pool thread. Provides `result`, `error`, `progress`, `finished` signals.
- `debounce(delay_ms)` — decorator that delays function execution until `delay_ms` of inactivity

### UiUtils
[app/utils/ui_utils.py](app/utils/ui_utils.py)

- `show_toast(parent, message, level, duration)` — InfoBar wrapper
- `show_confirm_dialog(parent, title, content, yes_text, cancel_text)` — MessageBox wrapper

### LoggerUtils
[app/utils/logger_utils.py](app/utils/logger_utils.py)

- Configures `loguru` with console + file handlers
- `set_log_directory(path)` — set log output directory before first write
