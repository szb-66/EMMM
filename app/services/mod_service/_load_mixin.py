# app/services/mod_service/_load_mixin.py
"""Skeleton scanning, hydration, and archive .ini probing.

Extracted from the original monolithic ``mod_service.py`` per ADR 0001.
The Mixin must NOT define ``__init__``; it shares state via ``self`` on the
host ``ModService`` instance.
"""
import json
import os
import hashlib
import zipfile
from pathlib import Path
from typing import Tuple

from app.models.mod_item_model import (
    BaseModItem,
    ObjectItem,
    FolderItem,
    ModType,
    ModStatus,
    CharacterObjectItem,
    GenericObjectItem,
)
from app.core.constants import (
    PROPERTIES_JSON_NAME,
    CONTEXT_OBJECTLIST,
    CONTEXT_FOLDERGRID,
    OBJECT_THUMBNAIL_SUFFIX,
    OBJECT_THUMBNAIL_EXACT,
    FOLDER_PREVIEW_PREFIX,
    SUPPORTED_IMAGE_EXTENSIONS,
    PIN_SUFFIX,
    DISABLED_PREFIX_PATTERN,
)
from app.utils.logger_utils import logger
import patoolib


class _LoadMixin:
    # --- Skeleton scanning, hydration, and archive probing ---

    def _parse_folder_name(self, folder_name: str) -> Tuple[str, ModStatus, bool]:
        """
        A robust helper to parse status and pin state from a folder name.
        Returns a tuple of (actual_name, status, is_pinned).
        """
        # Use regex for robust prefix matching (e.g., 'DISABLED ', 'disabled_')
        match = DISABLED_PREFIX_PATTERN.match(folder_name)
        if match:
            status = ModStatus.DISABLED
            # Remove the matched prefix part from the name
            clean_name = folder_name[match.end() :]
        else:
            status = ModStatus.ENABLED
            clean_name = folder_name

        # Check and remove pin suffix
        is_pinned = clean_name.lower().endswith(PIN_SUFFIX)
        if is_pinned:
            clean_name = clean_name[: -len(PIN_SUFFIX)]

        return clean_name.strip(), status, is_pinned

    def get_item_skeletons(self, path: Path, context: str) -> dict:
        """
        Flow 2.2: Scans a directory to create skeleton models quickly and robustly.
        """
        logger.info(f"Scanning for skeletons in '{path}' with context '{context}'")
        skeletons = []
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if not entry.is_dir():
                        continue

                    # 1. Parse name, status, and pin state using the helper
                    actual_name, status, is_pinned = self._parse_folder_name(entry.name)
                    item_path = Path(entry.path)

                    # 2. Generate a stable, unique ID using relative path and SHA1
                    relative_path = item_path.relative_to(path)
                    # Include the parent path context to prevent hash collisions
                    # when same-named folders exist under different parent directories
                    # (e.g., character "妮可" exists in both GIMI and ZZMI games).
                    id_input = f"{path.as_posix()}/{relative_path.as_posix()}"
                    item_id = hashlib.sha1(
                        id_input.encode("utf-8")
                    ).hexdigest()

                    # 3. Create the appropriate skeleton model based on context
                    skeleton: BaseModItem | None = None
                    if context == CONTEXT_OBJECTLIST:
                        object_type = ModType.OTHER
                        # Peek into properties.json just to get the type
                        try:
                            props_path = item_path / PROPERTIES_JSON_NAME
                            if props_path.is_file():
                                with open(props_path, "r", encoding="utf-8") as f:
                                    object_type = ModType(
                                        json.load(f).get("object_type", "Other")
                                    )
                        except (json.JSONDecodeError, KeyError, ValueError) as e:
                            logger.warning(
                                f"Could not parse object_type for '{actual_name}': {e}. Defaulting to 'Other'."
                            )

                        # Instantiate the correct skeleton class based on type
                        skeleton_class = (
                            CharacterObjectItem
                            if object_type == ModType.CHARACTER
                            else GenericObjectItem
                        )
                        skeleton = skeleton_class(
                            id=item_id,
                            actual_name=actual_name,
                            folder_path=item_path,
                            status=status,
                            is_pinned=is_pinned,
                            object_type=object_type,
                        )

                    elif context == CONTEXT_FOLDERGRID:
                        skeleton = FolderItem(
                            id=item_id,
                            actual_name=actual_name,
                            folder_path=item_path,
                            status=status,
                            is_pinned=is_pinned,
                        )

                    if skeleton:
                        skeletons.append(skeleton)

            return {"success": True, "items": skeletons, "error": None}

        except FileNotFoundError:
            msg = f"Invalid path specified for skeleton scan: {path}"
            logger.error(msg)
            return {"success": False, "items": [], "error": msg}
        except PermissionError:
            msg = f"Permission denied while scanning: {path}"
            logger.error(msg)
            return {"success": False, "items": [], "error": msg}

    def hydrate_item(
        self, skeleton_item: BaseModItem, game_name: str, context: str
    ) -> BaseModItem:
        """
        Flow 2.2 & 2.3: Hydrates a single skeleton item with detailed data.
        This version is robust and handles all item types correctly.
        """
        if not skeleton_item.is_skeleton:
            return skeleton_item

        try:
            # --- CONTEXT: OBJECTLIST (Character, Weapon, etc.) ---
            if isinstance(skeleton_item, ObjectItem):
                props_path = skeleton_item.folder_path / PROPERTIES_JSON_NAME
                properties = {}
                needs_json_update = False

                # 1. Load local properties.json first
                if props_path.is_file():
                    try:
                        with open(props_path, "r", encoding="utf-8") as f:
                            properties = json.load(f)
                    except json.JSONDecodeError:
                        logger.warning(f"{PROPERTIES_JSON_NAME} for '{skeleton_item.actual_name}' is corrupted. Rebuilding.")
                        properties = {} # Treat as empty if corrupt

                # 2. Check if essential data is missing for this type

                # --- Reality Check (Suffix Logic) ---
                found_thumb_path: Path | None = None
                for file in skeleton_item.folder_path.iterdir():
                    if (
                        file.is_file()
                        and file.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
                    ):
                        file_stem = file.stem.lower()  # Nama file tanpa ekstensi
                        if (
                            file_stem.endswith(OBJECT_THUMBNAIL_SUFFIX)
                            or file_stem in OBJECT_THUMBNAIL_EXACT
                        ):
                            found_thumb_path = file
                            break  # Ambil yang pertama ditemukan

                # --- Reconcile ---
                json_thumb_str = properties.get("thumbnail_path", "")
                if found_thumb_path and found_thumb_path.name != json_thumb_str:
                    logger.info(
                        f"Found physical thumbnail '{found_thumb_path.name}' for '{skeleton_item.actual_name}', updating JSON."
                    )
                    properties["thumbnail_path"] = found_thumb_path.name
                    needs_json_update = True

                # 5. If data was supplemented or thumbnail path changed, save the complete properties.json
                if needs_json_update:
                    self._write_json(props_path, properties)

                # 6. Build the final payload using the finalized 'properties' dictionary
                data_payload = {
                    "is_skeleton": False,
                    "tags": properties.get("tags", []),
                    "thumbnail_path": (
                        skeleton_item.folder_path / p
                        if (p := properties.get("thumbnail_path"))
                        else None
                    ),
                }

                if isinstance(skeleton_item, CharacterObjectItem):
                    data_payload.update({
                        "rarity": properties.get("rarity"),
                        "element": properties.get("element"),
                        "gender": properties.get("gender"),
                        "weapon": properties.get("weapon"),
                        "region": properties.get("region"),
                    })
                elif isinstance(skeleton_item, GenericObjectItem):
                    data_payload.update({"subtype": properties.get("subtype")})

                return dataclasses.replace(skeleton_item, **data_payload)

            # --- CONTEXT: FOLDERGRID (Final Mods or Navigable Folders) ---
            elif isinstance(skeleton_item, FolderItem):
                info_path = skeleton_item.folder_path / INFO_JSON_NAME

                # --- Check if this is a navigable folder (no .ini files) ---
                has_ini = any(
                    p.suffix.lower() == ".ini"
                    for p in skeleton_item.folder_path.iterdir()
                )

                if not has_ini:
                    # It's a navigable folder — still scan for preview images
                    # so collection folders can show thumbnails.
                    info = {}
                    needs_json_update = False

                    if info_path.is_file():
                        try:
                            with open(info_path, "r", encoding="utf-8") as f:
                                info = json.load(f)
                        except json.JSONDecodeError:
                            needs_json_update = True
                    else:
                        needs_json_update = True

                    # --- Reality Check ---
                    found_images = sorted(
                        [
                            p
                            for p in skeleton_item.folder_path.iterdir()
                            if p.is_file()
                            and p.stem.lower().startswith(FOLDER_PREVIEW_PREFIX)
                            and p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
                        ]
                    )

                    # --- Reconcile ---
                    json_image_paths = {
                        skeleton_item.folder_path / p
                        for p in info.get("image_paths", [])
                    }
                    if set(found_images) != json_image_paths:
                        logger.info(
                            f"Physical image files for navigable folder '{skeleton_item.actual_name}' "
                            "do not match info.json. Syncing."
                        )
                        info["image_paths"] = [p.name for p in found_images]
                        needs_json_update = True

                    if needs_json_update:
                        self._write_json(info_path, info)

                    image_paths = [
                        skeleton_item.folder_path / img
                        for img in info.get("image_paths", [])
                    ]

                    return dataclasses.replace(
                        skeleton_item,
                        is_navigable=True,
                        is_skeleton=False,
                        preview_images=image_paths,
                    )

                # It's a final mod, read info.json
                info = {}
                needs_json_update = False

                if info_path.is_file():
                    try:
                        with open(info_path, "r", encoding="utf-8") as f:
                            info = json.load(f)
                    except json.JSONDecodeError:
                        needs_json_update = True
                else:
                    needs_json_update = True

                # --- Reality Check (Prefix Logic) ---
                found_images = sorted(
                    [
                        p
                        for p in skeleton_item.folder_path.iterdir()
                        if p.is_file()
                        and p.stem.lower().startswith(FOLDER_PREVIEW_PREFIX)
                        and p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
                    ]
                )

                # --- Reconcile ---
                json_image_paths = {
                    skeleton_item.folder_path / p for p in info.get("image_paths", [])
                }
                if set(found_images) != json_image_paths:
                    logger.info(
                        f"Physical image files for '{skeleton_item.actual_name}' do not match info.json. Syncing."
                    )
                    info["image_paths"] = [p.name for p in found_images]
                    needs_json_update = True

                if needs_json_update:
                    self._write_json(info_path, info)

                image_paths = [
                    skeleton_item.folder_path / img
                    for img in info.get("image_paths", [])
                ]

                return dataclasses.replace(
                    skeleton_item,
                    author=info.get("author"),
                    description=info.get("description", ""),
                    tags=info.get("tags", []),
                    preview_images=image_paths,
                    is_safe=info.get("is_safe", False),
                    preset_name=info.get("preset_name"),
                    is_navigable=False,
                    is_skeleton=False,
                )

        except PermissionError:
            logger.error(
                f"Permission denied while hydrating: {skeleton_item.folder_path}"
            )

        # Fallback if something goes wrong
        logger.warning(
            f"Hydration failed for '{skeleton_item.actual_name}'. Returning skeleton."
        )
        return skeleton_item

    # --- Core Item Actions ---
    def _find_ini_recursively(self, root_path: Path, max_depth: int) -> bool:
        """
        [NEW HELPER] Recursively searches for any .ini file within a directory
        up to a specified maximum depth.
        """
        # We check from depth 0 (the root itself) to max_depth
        for i in range(max_depth + 1):
            # Create a glob pattern for the current depth
            # '*/' * i creates things like '', '*/', '*/*/', etc.
            pattern = '*/' * i + '*.ini'
            try:
                # Check if any file matches the pattern at this depth
                if next(root_path.glob(pattern), None):
                    return True # Found an .ini file, no need to search further
            except Exception as e:
                # This can happen with very long paths or permission issues
                logger.warning(f"Error while scanning for .ini files at depth {i}: {e}")
                return False # Stop searching on error
        return False # No .ini file found within the depth limit

    def _archive_has_ini(self, path: Path) -> bool:
        """
        [HELPER] Detects whether an archive contains any .ini file *without*
        extracting it. For ZIP-family containers we use the stdlib zipfile
        namelist (instant, no subprocess). For other formats (rar, 7z, tar,
        etc.) we deliberately return False to avoid the heavyweight
        extract-to-temp probing that previously blocked the UI thread on
        large archives — the caller will fall back to the has_ini_warning
        toast, which is a benign UX hint, not a correctness gate.
        """
        suffix = path.suffix.lower()
        try:
            if suffix == ".zip" or suffix in {".jar", ".whl", ".apk"}:
                with zipfile.ZipFile(path, "r") as zf:
                    for name in zf.namelist():
                        if name.lower().endswith(".ini"):
                            return True
                return False
        except (zipfile.BadZipFile, OSError) as e:
            logger.warning(f"Cannot read zip namelist for '{path.name}': {e}")
            return False

        # Non-zip formats: skip probing to keep analyze fast and crash-safe.
        logger.debug(
            f"Skipping .ini probing for non-zip archive '{path.name}' (suffix={suffix})."
        )
        return False

