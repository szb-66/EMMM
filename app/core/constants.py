# app/core/constants.py
import re

# --- Application Info ---
APP_NAME: str = "EMM Manager"
ORG_NAME: str = "reynalivan"
APP_ICON_PATH: str = "app/assets/images/icon.jpeg"
APP_VERSION: str = "0.0.1"

# --- Folder Naming Conventions ---
DISABLED_PREFIX_PATTERN = re.compile(r"^(disabled)[\s_]+", re.IGNORECASE)
DEFAULT_DISABLED_PREFIX: str = "DISABLED "
PIN_SUFFIX: str = "_pin"

# --- File & Directory Names ---
CONFIG_FILE_NAME: str = "config.json"
SCHEMA_FILE_NAME: str = "schema.json"
CACHE_DIR_NAME: str = "cache"
LOG_DIR_NAME: str = "logs"
PROPERTIES_JSON_NAME: str = "properties.json"  # For objectlist items
INFO_JSON_NAME: str = "info.json"  # For foldergrid items
INI_BACKUP_EXTENSION: str = ".backup"

# --- Thumbnail & Image Constants ---
OBJECT_THUMBNAIL_SUFFIX: str = "_thumb"
OBJECT_THUMBNAIL_EXACT: set[str] = {"thumb", "folder"}  # Nama file tanpa ekstensi
FOLDER_PREVIEW_PREFIX: str = "preview"
SUPPORTED_IMAGE_EXTENSIONS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp")
DEFAULT_ICONS: dict[str, str] = {
    "object": "app/assets/images/default_object.jpg",
    # Used for navigable folders in the foldergrid
    "folder": "app/assets/images/folder.jpg",
    # Used for final mods in the foldergrid that have no preview image
    "mod_placeholder": "app/assets/images/mod_placeholder.jpg",
}
# --- UI & Interaction Constants ---
DEBOUNCE_DELAY_MS: int = 300
CONTEXT_OBJECTLIST: str = "objectlist"
CONTEXT_FOLDERGRID: str = "foldergrid"

# --- Drag & Drop (internal mod reordering) ---
EMMM_MOD_MIME_TYPE: str = "application/x-emmm-mod"

# --- .ini File Parsing Constants ---
INI_CONSTANTS_SECTION: str = "Constants"

# --- XXMI Launcher Detection ---
KNOWN_XXMI_FOLDERS = {"GIMI", "SRMI", "WWMI"}
