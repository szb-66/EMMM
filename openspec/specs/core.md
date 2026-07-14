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
| `EMMM_MOD_MIME_TYPE` | `"application/x-emmm-mod"` | Custom MIME type for internal drag-and-drop of mods |

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

- Configures stdlib `logging` with a console handler (INFO+, compact `name:func:line` cyan location, green timestamp) and a `RotatingFileHandler` (DEBUG, full fields, 5 MiB × 10 backups).
- `set_log_directory(path)` — set log output directory before first write

#### Requirement: Console handler emits INFO and above

The console (stdout) handler SHALL emit only records at `INFO` level and above. The logger itself SHALL remain at `DEBUG` so that the file handler still receives `DEBUG` records. `DEBUG` records SHALL NOT appear on stdout.

##### Scenario: DEBUG call does not reach console
- **WHEN** any caller invokes `logger.debug(...)` during a normal run
- **THEN** the message is written to the rotating log file only, and is not written to stdout

##### Scenario: INFO call reaches console and file
- **WHEN** any caller invokes `logger.info(...)`
- **THEN** the message appears on stdout (colored) AND in the rotating log file

#### Requirement: Console line uses compact location format

The console formatter SHALL emit the call site as `<logger name>:<function>:<line>` only. It SHALL NOT prepend the verbose `File "<absolute path>", line <n> |` prefix. The file formatter is unchanged and retains full path information.

##### Scenario: Console line shape
- **WHEN** any record at `INFO` or above is formatted for the console handler
- **THEN** the location segment is `<name>:<funcName>:<lineno>` and contains no `File "` substring

#### Requirement: File handler retains full DEBUG fidelity

The rotating file handler SHALL remain at `DEBUG`, shall write every record the logger processes, and shall keep its existing field set (`asctime`, `levelname`, `name:funcName:lineno`, `message`). The change to console level/format SHALL NOT alter file output.

##### Scenario: DEBUG written to file after console quieting
- **WHEN** a `logger.debug(...)` call is made
- **THEN** the record is present in the current `LOG_EMMM_*.log` file with full fields

## i18n

[app/core/i18n.py](app/core/i18n.py)

JSON-driven translation engine with zero external dependencies.

| Attribute/Function | Description |
|---|---|
| `tr(key, **fmt)` | Look up translation key in active locale dict; fallback to English, then raw key. Supports `str.format(**fmt)` interpolation. |
| `set_language(lang)` | Switch active language by loading `app/assets/locales/{lang}.json` |
| `get_current_language()` | Return current language code (`"en"` or `"zh"`) |
| `AVAILABLE_LANGUAGES` | `{"en": "English", "zh": "中文"}` |
| `DEFAULT_LANGUAGE` | `"zh"` — Chinese is the default language |

### Locale files

- `app/assets/locales/en.json` — 328 translation keys
- `app/assets/locales/zh.json` — 328 translation keys
- Keys follow dot-separated namespaces: `common.*`, `main.*`, `settings.*`, `vm.*`, `foldergrid.*`, `objectlist.*`, `preview.*`, `thumb.*`, etc.
- Module self-check (`if __name__ == "__main__"`) asserts key parity across all locale files

### Fallback chain

Active locale → English (`en.json`) → raw key string.

### Usage pattern

All UI strings are resolved at widget construction time via `tr()`. Language changes require application restart (widgets call `tr()` in `__init__`). Language preference is persisted in `config.json` under `language` field.
