# app/services/mod_service.py
import shutil
import time
import uuid
import os
import json
import patoolib
import tempfile
import hashlib
import dataclasses
import zipfile
from pathlib import Path
from typing import Tuple, List
from app.utils.system_utils import SystemUtils
from PyQt6.QtGui import QImage
from PIL import Image


# Import models
from app.models.mod_item_model import (
    BaseModItem,
    ObjectItem,
    FolderItem,
    ModType,
    ModStatus,
    CharacterObjectItem,
    GenericObjectItem,
)

# Import constants for naming rules
from app.core.constants import (
    PROPERTIES_JSON_NAME,
    INFO_JSON_NAME,
    CONTEXT_OBJECTLIST,
    CONTEXT_FOLDERGRID,
    OBJECT_THUMBNAIL_SUFFIX,
    OBJECT_THUMBNAIL_EXACT,
    FOLDER_PREVIEW_PREFIX,
    SUPPORTED_IMAGE_EXTENSIONS,
    PIN_SUFFIX,
    DISABLED_PREFIX_PATTERN,
    DEFAULT_DISABLED_PREFIX,
)
from app.services.persist_utils import (
    find_game_root_from_folder,
    normalize_persist_key,
    read_user_persist_values,
    strip_disabled_prefix,
    write_user_persist_values,
)
from app.services.Iniparsing_service import IniKeyParsingService
from app.utils.logger_utils import logger

# Import other services for dependency injection
from app.services.database_service import DatabaseService
from app.utils.image_utils import ImageUtils


from app.services.mod_service._load_mixin import _LoadMixin
from app.services.mod_service._toggle_mixin import _ToggleMixin
from app.services.mod_service._crud_mixin import _CrudMixin
from app.services.mod_service._preview_mixin import _PreviewMixin
from app.services.mod_service._creation_mixin import _CreationMixin


class ModService(_CreationMixin, _PreviewMixin, _CrudMixin, _ToggleMixin, _LoadMixin):
    """Handles all atomic file system and JSON operations for a single mod item."""

    def __init__(
        self,
        database_service: DatabaseService,
        image_utils: ImageUtils,
        system_utils: SystemUtils,
        app_path: Path
    ):
        # --- Injected Services & Utilities ---
        self.database_service = database_service
        self.image_utils = image_utils
        self.system_utils = system_utils
        self.ini_parsing_service = IniKeyParsingService()
        self._app_path = app_path

    # --- Loading & Hydration ---
    def _write_json(self, json_path: Path, data: dict):
        """
        A helper function to safely write a dictionary to a JSON file.
        It uses an indent of 4 for human readability.
        """
        logger.debug(f"Writing updated data to {json_path}...")
        try:
            # Ensure the parent directory exists
            json_path.parent.mkdir(parents=True, exist_ok=True)

            with open(json_path, "w", encoding="utf-8") as f:
                # Use indent=4 to make the JSON file readable
                json.dump(data, f, indent=4)
        except (IOError, PermissionError) as e:
            logger.error(f"Failed to write to JSON file {json_path}: {e}")
