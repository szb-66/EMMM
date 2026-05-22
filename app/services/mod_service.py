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
from .database_service import DatabaseService
from app.utils.image_utils import ImageUtils


class ModService:
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
                    item_id = hashlib.sha1(
                        relative_path.as_posix().encode("utf-8")
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
                if not any(
                    p.suffix.lower() == ".ini"
                    for p in skeleton_item.folder_path.iterdir()
                ):
                    return dataclasses.replace(
                        skeleton_item, is_navigable=True, is_skeleton=False
                    )

                # It's a final mod, read info.json
                info_path = skeleton_item.folder_path / INFO_JSON_NAME
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
    def toggle_status(
        self, item: BaseModItem, target_status: ModStatus | None = None
    ) -> dict:
        """
        Flow 3.1: Enables/disables a mod by renaming its folder.
        This is a core file system operation.

        Parameters
        ----------
        item : BaseModItem
            The mod item object to be toggled.
        target_status : ModStatus | None, optional
            If provided, forces the status to ENABLED or DISABLED (for bulk actions).
            If None, the status is inverted (for single toggles).

        Returns
        -------
        dict
            A dictionary indicating success or failure.
            On success: {"success": True, "data": {"new_path": Path, "new_status": ModStatus}}
            On failure: {"success": False, "error": "Error message"}
        """
        try:
            # check if path exists

            if not item.folder_path.exists():
                logger.warning(f"Folder path '{item.folder_path}' does not exist.")
                return {"success": False, "error": "Folder path does not exist."}

            # 1. Determine the new status
            if target_status is not None:
                # This path is for bulk actions. If status is already correct, do nothing.
                if item.status == target_status:
                    return {"success": True, "data": item}
                new_status = target_status
            else:
                # This path is for single toggles. Invert the current status.
                new_status = (
                    ModStatus.DISABLED
                    if item.status == ModStatus.ENABLED
                    else ModStatus.ENABLED
                )

            if isinstance(item, (FolderItem, ObjectItem)):
                if new_status == ModStatus.DISABLED:
                    sync_result = self._sync_runtime_persistent_state_to_source(item)
                    if not sync_result.get("success"):
                        return {
                            "success": False,
                            "error": sync_result.get(
                                "error",
                                "Failed to synchronize runtime persist state.",
                            ),
                        }
                    self._snapshot_persistent_state(
                        item, sync_result.get("snapshot")
                    )
                elif new_status == ModStatus.ENABLED:
                    self._restore_persistent_state_snapshot(item)

            # 2. Construct the new folder name
            prefix = DEFAULT_DISABLED_PREFIX if new_status == ModStatus.DISABLED else ""
            suffix = PIN_SUFFIX if item.is_pinned else ""
            new_name = f"{prefix}{item.actual_name}{suffix}"
            new_path = item.folder_path.with_name(new_name)
            logger.info(f"Renaming '{item.folder_path.name}' to '{new_path.name}'")

            # 3. Perform the rename operation
            os.rename(item.folder_path, new_path)

            # 4. --- Create a new model object with the changes ---
            data_to_update = {"folder_path": new_path, "status": new_status}
            new_item = dataclasses.replace(item, **data_to_update)

            # 5. Return success with the new data
            return {"success": True, "data": new_item}

        except FileExistsError:
            error_msg = f"Folder name conflict: '{new_path.name}' already exists."
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        except PermissionError:
            error_msg = "Permission denied. The folder or its contents may be in use by another program."
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"An unexpected error occurred during rename: {e}"
            logger.critical(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}

    def _sync_runtime_persistent_state_to_source(self, item: BaseModItem) -> dict:
        game_root = find_game_root_from_folder(item.folder_path)
        if not game_root:
            return {"success": True, "snapshot": {}, "updated_files": []}

        user_config_path = game_root / "d3dx_user.ini"
        if not user_config_path.is_file():
            return {"success": True, "snapshot": {}, "updated_files": []}

        return self.ini_parsing_service.sync_runtime_persist_to_source(
            item.folder_path, game_root
        )

    def _snapshot_persistent_state(
        self, item: BaseModItem, runtime_snapshot: dict[str, str] | None = None
    ) -> None:
        game_root = find_game_root_from_folder(item.folder_path)
        if not game_root:
            return

        user_config_path = game_root / "d3dx_user.ini"
        if not user_config_path.is_file():
            return

        snapshot: dict[str, str] = {}
        if runtime_snapshot:
            snapshot.update(
                {
                    normalize_persist_key(k): str(v)
                    for k, v in runtime_snapshot.items()
                }
            )

        # read_user_persist_values returns normalized keys
        prefix = self._persistent_key_prefix_for_folder(item.folder_path, game_root)
        for key, value in read_user_persist_values(user_config_path).items():
            if key.startswith(prefix):
                snapshot[key] = value

        if not snapshot:
            return

        info_path = self._metadata_path_for_item(item)
        info = self._read_json_or_empty(info_path)
        info["persistent_state_snapshot"] = snapshot
        self._write_json(info_path, info)
        logger.info(
            "Saved %d persistent state value(s) for '%s'.",
            len(snapshot),
            item.actual_name,
        )

    def _restore_persistent_state_snapshot(self, item: BaseModItem) -> None:
        game_root = find_game_root_from_folder(item.folder_path)
        if not game_root:
            return

        info = self._read_json_or_empty(self._metadata_path_for_item(item))
        snapshot = info.get("persistent_state_snapshot")
        if not isinstance(snapshot, dict) or not snapshot:
            return

        # Normalize keys for backward compatibility
        normalized = {normalize_persist_key(k): str(v) for k, v in snapshot.items()}
        user_config_path = game_root / "d3dx_user.ini"
        write_user_persist_values(user_config_path, normalized)
        logger.info(
            "Restored %d persistent state value(s) for '%s'.",
            len(normalized),
            item.actual_name,
        )

    def _persistent_key_prefix_for_folder(self, folder_path: Path, game_root: Path) -> str:
        try:
            relative_path = folder_path.relative_to(game_root)
        except ValueError:
            return ""

        normalized_parts = [
            strip_disabled_prefix(part) for part in relative_path.parts
        ]
        return normalize_persist_key(
            "$\\" + "\\".join(normalized_parts) + "\\"
        )

    def _read_json_or_empty(self, json_path: Path) -> dict:
        if not json_path.is_file():
            return {}
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _metadata_path_for_item(self, item: BaseModItem) -> Path:
        filename = PROPERTIES_JSON_NAME if isinstance(item, ObjectItem) else INFO_JSON_NAME
        return item.folder_path / filename

    def toggle_pin_status(self, item: BaseModItem) -> dict:
        """
        [NEW] Toggles the pinned state of an item by renaming its folder
        and updating the 'is_pinned' flag in its JSON file.
        """
        # Determine the correct JSON file based on the item's context
        is_objectlist_item = isinstance(item, ObjectItem)
        json_filename = PROPERTIES_JSON_NAME if is_objectlist_item else INFO_JSON_NAME

        original_path = item.folder_path

        try:
            # 1. Determine the new state and construct the new folder name
            new_pin_status = not item.is_pinned
            prefix = DEFAULT_DISABLED_PREFIX if item.status == ModStatus.DISABLED else ""
            suffix = PIN_SUFFIX if new_pin_status else "" # Add or remove the _pin suffix

            new_folder_name = f"{prefix}{item.actual_name}{suffix}"
            new_path = original_path.with_name(new_folder_name)

            # 2. Rename the folder
            logger.info(f"Toggling pin status: Renaming '{original_path.name}' to '{new_path.name}'")
            os.rename(original_path, new_path)

            # 3. Update the JSON file inside the newly renamed folder
            json_file_path = new_path / json_filename
            properties = {}
            if json_file_path.is_file():
                with open(json_file_path, "r", encoding="utf-8") as f:
                    properties = json.load(f)

            properties['is_pinned'] = new_pin_status
            self._write_json(json_file_path, properties)

            # 4. Return the new state
            updated_data = {
                "folder_path": new_path,
                "is_pinned": new_pin_status
            }
            new_item = dataclasses.replace(item, **updated_data)
            return {"success": True, "data": new_item, "item_id": item.id}

        except FileExistsError:
            error_msg = f"A folder named '{new_path.name}' already exists."
            return {"success": False, "error": error_msg, "item_id": item.id}
        except Exception as e:
            error_msg = f"Failed to toggle pin status for '{item.actual_name}': {e}"
            logger.error(error_msg, exc_info=True)
            # Attempt to roll back if rename was successful but JSON update failed
            if new_path.exists() and not original_path.exists():
                os.rename(new_path, original_path)
            return {"success": False, "error": error_msg, "item_id": item.id}

    def rename_item(self, item: BaseModItem, new_name: str) -> dict:
        """
        [REVISED] Renames a mod folder and its internal JSON file using a safer
        'read -> rename -> write' sequence to avoid file lock issues.
        """
        is_objectlist_item = isinstance(item, ObjectItem)
        json_filename = PROPERTIES_JSON_NAME if is_objectlist_item else INFO_JSON_NAME

        original_path = item.folder_path
        json_file_path_original = original_path / json_filename

        # --- THE CORE FIX: Read data BEFORE any file system modifications ---
        try:
            if json_file_path_original.is_file():
                with open(json_file_path_original, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                # If the JSON doesn't exist, start with an empty dictionary
                data = {}
        except Exception as e:
            error_msg = f"Failed to read JSON file before renaming: {e}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}
        # --- By this point, the file handle is closed and released ---

        # Update the name in memory
        data["actual_name"] = new_name

        # Construct the new path
        prefix = DEFAULT_DISABLED_PREFIX if item.status == ModStatus.DISABLED else ""
        suffix = PIN_SUFFIX if item.is_pinned else ""
        new_folder_name = f"{prefix}{new_name}{suffix}"
        new_path = original_path.with_name(new_folder_name)

        try:
            logger.info(f"Renaming folder from '{original_path.name}' to '{new_path.name}'")

            # Add a tiny delay to give the OS time to release any lingering handles
            time.sleep(0.05)

            # 1. Rename the folder on the filesystem
            os.rename(original_path, new_path)

            # 2. Write the modified data (already in memory) to the new location
            json_file_path_new = new_path / json_filename
            self._write_json(json_file_path_new, data)

            # Return the new state
            updated_data = {"folder_path": new_path, "actual_name": new_name}
            new_item = dataclasses.replace(item, **updated_data)
            return {"success": True, "data": new_item, "item_id": item.id}

        except FileExistsError:
            error_msg = f"A folder named '{new_path.name}' already exists."
            logger.warning(error_msg)
            return {"success": False, "error": str(e), "item_id": item.id}
        except Exception as e:
            # Attempt to roll back if something went wrong
            if new_path.exists() and not original_path.exists():
                logger.error(f"Error during rename process. Attempting to roll back folder rename...")
                os.rename(new_path, original_path)

            error_msg = f"Failed to rename item: {e}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": str(e), "item_id": item.id}

    def delete_item(self, item: BaseModItem) -> dict:
        """
        [NEW] Moves an item's folder to the system's recycle bin
        by delegating to SystemUtils.
        """
        logger.info(f"Request to move folder to recycle bin: {item.folder_path}")
        try:
            self.system_utils.move_to_recycle_bin(item.folder_path)

            logger.info(f"Successfully moved '{item.actual_name}' to recycle bin.")
            return {"success": True, "item_id": item.id, "item_name": item.actual_name}

        except Exception as e:
            error_msg = f"Failed to move '{item.actual_name}' to recycle bin: {e}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg, "item_id": item.id}


    # --- Creation Actions ---
    def create_foldergrid_item(self, parent_path: Path, task: dict) -> dict:
        """Flow 4.1.A: Creates a single new mod in foldergrid from a task dict."""
        # Handles creation from zip, folder, or manual input based on task type.
        # TODO: Implement actual creation logic
        return {}

    def create_objectlist_item(self, parent_path: Path, task: dict) -> dict:
        """Flow 4.1.B: Creates a single new object in objectlist from a task dict."""
        # Creates folder and a pre-filled properties.json.
        # TODO: Implement actual creation logic
        return {}

    # --- JSON & Metadata Updates ---
    def update_item_properties(self, item: FolderItem, data_to_update: dict) -> dict:
        """
        Flow 5.2, 6.2.A: Updates key-value pairs in an item's JSON file.
        This is a generic method for editing description, author, tags, etc.
        """
        if not isinstance(item, FolderItem):
            return {"success": False, "error": "Invalid item type for property update."}

        info_path = item.folder_path / INFO_JSON_NAME
        info = {}

        # Read existing data first (this part is correct)
        if info_path.is_file():
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    info = json.load(f)
            except json.JSONDecodeError:
                logger.warning(
                    f"Corrupted {INFO_JSON_NAME} for '{item.actual_name}'. It will be overwritten."
                )

        # Update the dictionary for JSON in memory with new data
        info.update(data_to_update)

        try:
            # Write the updated dictionary back to the JSON file
            self._write_json(info_path, info)

            # Prepare arguments for the dataclass, mapping JSON keys to dataclass fields if necessary.
            dataclass_args = data_to_update.copy()
            if "preview_images" in dataclass_args:
                base_path = item.folder_path
                string_paths = dataclass_args["preview_images"]
                # Create full Path objects for the in-memory model
                dataclass_args["preview_images"] = [base_path / p for p in string_paths]

            # Create a new immutable model with the correctly mapped updated data
            new_item = dataclasses.replace(item, **dataclass_args)
            # --- FIX ENDS HERE ---

            logger.info(f"Successfully updated properties for '{item.actual_name}'")
            return {"success": True, "data": new_item}

        except Exception as e:
            error_msg = f"Failed to save properties for '{item.actual_name}': {e}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}

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

    def add_preview_image(self, item: FolderItem, image_data) -> dict:
        """Flow 5.2 Part C: Adds a new preview image to a mod."""
        if not isinstance(item, FolderItem) or not image_data:
            return {"success": False, "error": "Invalid item or image data provided."}

        try:
            # 1. Use the utility to find the next available filename
            target_path = self.image_utils.find_next_available_preview_path(
                item.folder_path, base_name=FOLDER_PREVIEW_PREFIX
            )
            unique_name = target_path.name  # Get the relative name for JSON

            # 2. Process and save the image using the implemented utility
            self.image_utils.compress_and_save_image(
                source_image=image_data, target_path=target_path
            )

            # 3. Read current metadata
            info_path = item.folder_path / INFO_JSON_NAME
            info = {}
            if info_path.is_file():
                try:
                    with open(info_path, "r", encoding="utf-8") as f:
                        info = json.load(f)
                except json.JSONDecodeError:
                    logger.warning(
                        f"Corrupted {INFO_JSON_NAME} for '{item.actual_name}'."
                    )

            # 4. Update image list and save back using the helper method
            image_list = info.get("preview_images", [])
            image_list.append(unique_name)

            return self.update_item_properties(item, {"preview_images": image_list})

        except ValueError as e:  # Catches errors from compress_and_save_image
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(
                f"Failed to add preview image for '{item.actual_name}': {e}",
                exc_info=True,
            )
            return {"success": False, "error": f"An unexpected error occurred: {e}"}

    def _handle_image_removal(
        self, item: FolderItem, paths_to_delete: list[Path], final_image_list: list[str]
    ) -> dict:
        """
        A private helper to robustly handle the physical deletion of images
        and the subsequent metadata update.
        """
        if not paths_to_delete:
            # If there's nothing to delete, return success immediately.
            return {"success": True, "data": item, "deleted_paths": []}

        # 1. Attempt to delete all specified physical files, tracking results
        successfully_deleted_paths = []
        failed_deletions = []
        for full_path in paths_to_delete:
            if full_path.is_file():
                if self.system_utils.move_to_recycle_bin(full_path):
                    successfully_deleted_paths.append(full_path)
                else:
                    failed_deletions.append(full_path.name)
            else:
                logger.warning(f"Attempted to delete non-existent file: {full_path}")

        # 2. If any deletion failed, stop and report the error.
        if failed_deletions:
            error_msg = f"Failed to delete {len(failed_deletions)} image(s): {', '.join(failed_deletions)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

        # 3. Check for fallback (permanent) deletion warnings after all deletions
        fallback_warnings = SystemUtils.pop_fallback_warnings()
        if fallback_warnings:
            logger.warning(
                "%d image(s) were permanently deleted (recycle bin unavailable): %s",
                len(fallback_warnings), fallback_warnings,
            )

        # 4. If all deletions were successful, update the metadata with the new list.
        logger.info(
            f"Successfully deleted {len(successfully_deleted_paths)} image(s). Updating metadata."
        )
        update_result = self.update_item_properties(
            item, {"preview_images": final_image_list}
        )

        # 5. Augment the result with the list of deleted paths for cache invalidation.
        if update_result.get("success"):
            update_result["deleted_paths"] = successfully_deleted_paths
            if fallback_warnings:
                update_result["fallback_warnings"] = fallback_warnings

        return update_result

    def remove_preview_image(self, item: FolderItem, image_path: Path) -> dict:
        """
        Flow 5.2 Part C: Removes a single preview image from a mod.
        This method now prepares the data and delegates the core logic to a helper.
        """
        if (
            not isinstance(item, FolderItem)
            or not image_path
            or not image_path.is_file()
        ):
            return {"success": False, "error": "Invalid item or image path provided."}

        try:
            # Prepare the arguments for the helper
            info_path = item.folder_path / INFO_JSON_NAME
            current_image_list = []
            if info_path.is_file():
                with open(info_path, "r", encoding="utf-8") as f:
                    current_image_list = json.load(f).get("preview_images", [])

            # Create the new list of images for the JSON file
            final_image_list = [
                name for name in current_image_list if name != image_path.name
            ]

            # Delegate the actual work to the helper
            return self._handle_image_removal(
                item=item,
                paths_to_delete=[image_path],
                final_image_list=final_image_list,
            )
        except Exception as e:
            error_msg = (
                f"An unexpected error occurred while preparing to remove image: {e}"
            )
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}

    def remove_all_preview_images(self, item: FolderItem) -> dict:
        """
        Removes all preview images associated with a mod.
        This method now prepares the data and delegates the core logic to a helper.
        """
        if not isinstance(item, FolderItem):
            return {"success": False, "error": "Invalid item type for this operation."}

        try:
            # Prepare the arguments for the helper
            info_path = item.folder_path / INFO_JSON_NAME
            if not info_path.is_file():
                return {"success": True, "data": item, "deleted_paths": []}

            with open(info_path, "r", encoding="utf-8") as f:
                relative_paths_to_delete = json.load(f).get("preview_images", [])

            # Create a list of full Path objects to delete
            full_paths_to_delete = [
                item.folder_path / name for name in relative_paths_to_delete
            ]

            # Delegate the actual work to the helper
            return self._handle_image_removal(
                item=item,
                paths_to_delete=full_paths_to_delete,
                final_image_list=[],  # The final list will be empty
            )
        except Exception as e:
            error_msg = (
                f"An unexpected error occurred while preparing to clear images: {e}"
            )
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}

    def reorder_preview_images(self, item: FolderItem, new_order: list[Path]) -> dict:
        """
        Reorders the preview images list for a mod. Used to set a specific image
        as the cover by moving it to index 0.
        """
        if not isinstance(item, FolderItem):
            return {"success": False, "error": "Invalid item type."}

        try:
            # Convert Path objects to relative names (as stored in info.json)
            image_names = [
                p.relative_to(item.folder_path).as_posix()
                if p.is_absolute()
                else p
                for p in new_order
            ]
            return self.update_item_properties(
                item, {"preview_images": image_names}
            )
        except Exception as e:
            error_msg = f"Failed to reorder preview images: {e}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}

    def create_manual_object(self, parent_path: Path, object_data: dict) -> dict:
        """
        [FINAL REVISION] Creates a new object folder, populates properties.json,
        and correctly processes a thumbnail from either a file path or clipboard image data.
        """
        folder_name = object_data.get("name")
        if not folder_name:
            # This case should be prevented by the dialog's validation, but as a safeguard:
            return {"success": False, "error": "Folder name cannot be empty."}

        folder_path = parent_path / folder_name

        try:
            logger.info(f"Ensuring object folder exists at: {folder_path}")
            folder_path.mkdir(exist_ok=True)

            # --- Thumbnail Processing Logic ---
            # Prioritize a manually selected source (from dialog) over a DB source.
            thumbnail_source = object_data.get("thumbnail_source")
            db_thumb_path_str = object_data.get("thumbnail_path")
            final_thumb_name = ""

            if thumbnail_source or db_thumb_path_str:
                try:
                    dest_thumb_path = folder_path / "_thumb.png"

                    if thumbnail_source:
                        if isinstance(thumbnail_source, Path):
                            # Case 1: The source is a file Path from the "Browse..." button
                            logger.info(f"Copying thumbnail from path: {thumbnail_source}")
                            # Optional: Add image compression via ImageUtils here before copying
                            shutil.copy(thumbnail_source, dest_thumb_path)
                            final_thumb_name = dest_thumb_path.name

                        elif isinstance(thumbnail_source, Image.Image):
                            # Case 2: Source is a PIL Image object from "Paste"
                            logger.info("Saving thumbnail from clipboard (PIL Image) data.")
                            thumbnail_source.save(dest_thumb_path, "PNG")
                            final_thumb_name = dest_thumb_path.name

                        elif isinstance(thumbnail_source, QImage):
                            # Case 3: The source is QImage data from "Paste"
                            logger.info("Saving thumbnail from clipboard image data.")
                            # QImage has a built-in save method
                            if thumbnail_source.save(str(dest_thumb_path), "PNG"):
                                final_thumb_name = dest_thumb_path.name
                            else:
                                logger.error(f"Failed to save QImage to {dest_thumb_path}")
                    elif db_thumb_path_str:
                        # Case 2: Source is a path string from a database sync task
                        source_thumb_path = self._app_path / Path(db_thumb_path_str)
                        if source_thumb_path.is_file():
                            logger.info(f"Copying database thumbnail from path: {source_thumb_path}")
                            shutil.copy(source_thumb_path, dest_thumb_path)
                            final_thumb_name = dest_thumb_path.name
                        else:
                            logger.warning(f"Database thumbnail not found, skipping copy: {source_thumb_path}")

                except Exception as e:
                    logger.error(f"Failed to process thumbnail for '{folder_name}': {e}", exc_info=True)
                    # Continue without a thumbnail if processing fails
            # --- End of Thumbnail Processing ---

            # --- Prepare properties.json data ---
            properties = {
                "id": f"emm-obj-{uuid.uuid4()}",
                "actual_name": folder_name,
                "is_pinned": False,
                "object_type": object_data.get("object_type", "Other"),
                "thumbnail_path": final_thumb_name, # Use the final, processed thumbnail name
                "tags": object_data.get("tags", []),
                # Get all other potential metadata from the creation task
                "rarity": object_data.get("rarity"),
                "element": object_data.get("element"),
                "gender": object_data.get("gender"),
                "weapon": object_data.get("weapon"),
                "subtype": object_data.get("subtype"),
                "region": object_data.get("region"),
                "release_date": object_data.get("release_date"),
            }

            # Remove keys with None values to keep the JSON file clean
            properties = {k: v for k, v in properties.items() if v is not None}

            # Write the final properties.json file
            self._write_json(folder_path / PROPERTIES_JSON_NAME, properties)

            logger.info(f"Successfully created object '{folder_name}' with full metadata.")
            return {"success": True, "data": {"folder_path": folder_path}}

        except PermissionError:
            error_msg = "Permission denied. Could not create folder."
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"An unexpected error occurred: {e}"
            logger.critical(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}

    def convert_object_type(self, item_id: str, item_path: Path, new_type_str: str) -> dict:
        """
        Changes the 'object_type' within an item's properties.json file.
        This is an atomic file operation.
        """
        props_path = item_path / PROPERTIES_JSON_NAME

        try:
            # 1. Read the existing properties.json
            if not props_path.is_file():
                # If the file doesn't exist, create a basic structure
                logger.warning(f"'{PROPERTIES_JSON_NAME}' not found for item at '{item_path}'. Creating a new one.")
                properties = {}
            else:
                with open(props_path, "r", encoding="utf-8") as f:
                    properties = json.load(f)

            # 2. Update the object_type value
            logger.info(f"Converting object '{item_path.name}' to type '{new_type_str}'.")
            properties["object_type"] = new_type_str

            # 3. Write the changes back to the file
            self._write_json(props_path, properties)

            # Return success
            return {"success": True, "item_id": item_id}

        except (IOError, json.JSONDecodeError) as e:
            error_msg = f"Failed to read or write {props_path}: {e}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"An unexpected error occurred during type conversion: {e}"
            logger.critical(error_msg, exc_info=True)
            return {"success": False, "error": error_msg}

    def update_object_properties_from_db(self, item: ObjectItem, db_data: dict) -> dict:
        """
        [NEW] Updates an object's local properties.json with data from a
        matched database entry and copies the thumbnail.
        """
        props_path = item.folder_path / PROPERTIES_JSON_NAME
        properties = {}

        # 1. Read existing local data
        if props_path.is_file():
            with open(props_path, "r", encoding="utf-8") as f:
                properties = json.load(f)

        # 2. Merge data: DB data is the base, local data overwrites it
        # This preserves local settings like 'is_pinned'
        final_data = db_data.copy()
        final_data.update(properties)

        # 3. Handle thumbnail copy
        source_thumb_path_str = db_data.get("thumbnail_path")
        if source_thumb_path_str:
            try:
                source_thumb_path = self._app_path / Path(source_thumb_path_str) # Assuming self._app_path exists
                dest_thumb_filename = f"_thumb{source_thumb_path.suffix}"
                dest_thumb_path = item.folder_path / dest_thumb_filename

                if source_thumb_path.is_file():
                    shutil.copy(source_thumb_path, dest_thumb_path)
                    final_data["thumbnail_path"] = dest_thumb_filename
                else:
                    logger.warning(f"DB thumbnail not found: {source_thumb_path}")
            except Exception as e:
                logger.error(f"Failed to copy DB thumbnail for '{item.actual_name}': {e}")

        # 4. Write the updated and merged data back to properties.json
        try:
            self._write_json(props_path, final_data)
            return {"success": True, "item_id": item.id}
        except Exception as e:
            error_msg = f"Failed to write updated properties for '{item.actual_name}': {e}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg, "item_id": item.id}

    def update_object(self, item: ObjectItem, update_data: dict) -> dict:
        """
        [NEW] Updates an object's folder and properties.json file based on
        the provided data from the edit dialog.
        """
        original_path = item.folder_path
        new_name = update_data.get("name", item.actual_name)

        current_path = original_path
        needs_rename = new_name != item.actual_name

        try:
            # --- 1. Handle Folder Rename (if name changed) ---
            if needs_rename:
                prefix = DEFAULT_DISABLED_PREFIX if item.status == ModStatus.DISABLED else ""
                suffix = PIN_SUFFIX if item.is_pinned else ""
                new_folder_name = f"{prefix}{new_name}{suffix}"
                new_path = original_path.with_name(new_folder_name)

                logger.info(f"Renaming object folder from '{original_path.name}' to '{new_path.name}'")
                os.rename(original_path, new_path)
                current_path = new_path # Use the new path for subsequent operations

            # --- 2. Read existing JSON data ---
            json_filename = PROPERTIES_JSON_NAME
            props_path = current_path / json_filename
            properties = {}
            if props_path.is_file():
                with open(props_path, "r", encoding="utf-8") as f:
                    properties = json.load(f)

            # --- 3. Update properties with new data ---
            properties.update({
                "actual_name": new_name,
                "object_type": update_data.get("object_type"),
                "rarity": update_data.get("rarity"),
                "element": update_data.get("element"),
                "gender": update_data.get("gender"),
                "weapon": update_data.get("weapon"),
                "subtype": update_data.get("subtype"),
                "tags": update_data.get("tags", []),
            })

            # --- 4. Process new thumbnail if provided ---
            thumbnail_source = update_data.get("thumbnail_source")
            if thumbnail_source:
                dest_thumb_path = current_path / "_thumb.png"
                if isinstance(thumbnail_source, Path):
                    shutil.copy(thumbnail_source, dest_thumb_path)
                elif isinstance(thumbnail_source, (Image.Image, QImage)):
                    thumbnail_source.save(str(dest_thumb_path), "PNG")

                properties["thumbnail_path"] = dest_thumb_path.name
                logger.info(f"Updated thumbnail for '{new_name}'.")

            # --- 5. Write updated JSON back to disk ---
            properties = {k: v for k, v in properties.items() if v is not None}
            self._write_json(props_path, properties)

            logger.info(f"Successfully updated object '{new_name}'.")
            return {"success": True, "item_id": item.id}

        except Exception as e:
            error_msg = f"Failed to update object '{item.actual_name}': {e}"
            logger.error(error_msg, exc_info=True)
            # Attempt to roll back rename if it happened
            if needs_rename and current_path.exists() and not original_path.exists():
                os.rename(current_path, original_path)
            return {"success": False, "error": error_msg, "item_id": item.id}

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

    def analyze_source_path(self, path: Path) -> dict:
        """
        [NEW] Performs a quick, non-blocking analysis of a source path
        (folder or archive) to propose a creation task.
        """
        proposed_name = ""
        has_ini_warning = False
        is_valid = False
        error_message = ""

        try:
            if path.is_dir():
                is_valid = True
                proposed_name = path.name
                # Check for .ini files in the top level of the folder
                if not self._find_ini_recursively(path, max_depth=5):
                    has_ini_warning = True

            elif path.is_file() and patoolib.is_archive(str(path)):
                is_valid = True
                proposed_name = path.stem # Name without extension
                # Safely extract to a temporary directory to check for .ini files
                with tempfile.TemporaryDirectory(prefix="EMM_analyze_") as temp_dir:
                    temp_path = Path(temp_dir)
                    patoolib.extract_archive(str(path), outdir=str(temp_path), verbosity=-1)

                    # Check for .ini files in the extracted contents
                    if not self._find_ini_recursively(temp_path, max_depth=5):
                        has_ini_warning = True
                # The temporary directory is automatically cleaned up here
            else:
                error_message = "Unsupported file type."

        except patoolib.util.PatoolError as e:
            logger.warning(f"Could not analyze archive {path.name}: {e}")
            error_message = "Corrupt or encrypted archive."
        except Exception as e:
            logger.error(f"Unexpected error analyzing path {path}: {e}")
            error_message = "An unexpected error occurred."

        return {
            "source_path": path,
            "proposed_name": proposed_name,
            "has_ini_warning": has_ini_warning,
            "is_valid": is_valid,
            "error_message": error_message,
        }

    def create_mod_from_source(self, source_path: Path, output_name: str, parent_path: Path, cancel_flag: List[bool]) -> dict:
        """
        [NEW] Creates a new mod folder by either copying a directory or
        extracting an archive. This operation is cancellable.
        """
        if cancel_flag:
            return {"status": "cancelled"}
        final_output_name = f"{DEFAULT_DISABLED_PREFIX}{output_name}"
        output_path = parent_path / final_output_name

        if output_path.exists():
            return {"success": False, "error": f"Folder '{output_name}' already exists."}

        try:
            # --- Case 1: Source is a standard Folder ---
            if source_path.is_dir():
                logger.info(f"Copying folder from '{source_path}' to '{output_path}'")
                shutil.copytree(source_path, output_path)

            # --- Case 2: Source is an Archive ---
            elif source_path.is_file():
                logger.info(f"Extracting archive '{source_path.name}'...")

                with tempfile.TemporaryDirectory(prefix="EMM_extract_") as temp_dir:
                    temp_path = Path(temp_dir)

                    # 1. Initial Extraction (This will catch password errors)
                    patoolib.extract_archive(str(source_path), outdir=str(temp_path), verbosity=-1, interactive=False)

                    # 2. Analyze the contents of the temporary directory
                    extracted_contents = os.listdir(temp_path)

                    # --- Handle Empty Archive ---
                    if not extracted_contents:
                        raise ValueError("The provided archive is empty.")

                    # --- Smart Extraction Logic ---
                    source_for_copy = temp_path
                    if len(extracted_contents) == 1:
                        single_item_path = temp_path / extracted_contents[0]
                        if single_item_path.is_dir():
                            # Case 2a: Single root folder inside the archive.
                            # We'll copy the *contents* of this folder.
                            logger.info(f"Archive contains a single root folder ('{extracted_contents[0]}'). Copying its contents.")
                            source_for_copy = single_item_path

                    # Case 2b (else): Multiple items at the root.
                    # We'll copy everything from the temp directory root.
                    if source_for_copy == temp_path:
                        logger.info("Archive contains multiple root items. Copying all extracted content.")

                    # 3. Final Copy Operation
                    shutil.copytree(source_for_copy, output_path)

            # Final check for cancellation before returning success
            if cancel_flag:
                logger.warning(f"Operation cancelled after processing '{output_name}'. Cleaning up...")
                if output_path.exists():
                    shutil.rmtree(output_path)
                return {"status": "cancelled"}

            # Create a default info.json
            self._write_json(output_path / INFO_JSON_NAME, {"actual_name": output_name})

            return {
                "success": True,
                "skeleton_data": {
                    "id": self.system_utils.generate_item_id(output_path, parent_path),
                    "actual_name": output_name,
                    "folder_path": output_path,
                    "status": ModStatus.DISABLED, # New mods are disabled by default
                    "is_pinned": False,
                    "is_skeleton": True # It's a skeleton until hydrated
                }
            }

        except patoolib.util.PatoolError as e:
            error_str = str(e).lower()
            if "password" in error_str or "incorrect password" in error_str:
                logger.warning(f"Archive '{source_path.name}' is password-protected.")
                return {"status": "password_required", "error": "Archive is password-protected."}
            else:
                error_msg = f"Archive Error: {source_path.name}. It may be corrupt."
                logger.error(f"{error_msg} - Details: {e}")
                return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"Failed to process '{source_path.name}': {e}"
            logger.error(error_msg, exc_info=True)
            if output_path.exists():
                shutil.rmtree(output_path) # Clean up partial creations
            return {"success": False, "error": error_msg}

    def cleanup_lingering_temp_folders(self):
        """
        [NEW] Scans the system's temporary directory for leftover folders
        from previous sessions and removes them.
        """
        temp_dir = Path(tempfile.gettempdir())
        prefix = "EMM_extract_"
        logger.info(f"Scanning for leftover temporary folders with prefix '{prefix}' in '{temp_dir}'...")

        folders_to_delete = [d for d in temp_dir.iterdir() if d.is_dir() and d.name.startswith(prefix)]

        if not folders_to_delete:
            logger.info("No leftover temporary folders found.")
            return

        deleted_count = 0
        for folder in folders_to_delete:
            try:
                shutil.rmtree(folder)
                logger.info(f"Successfully removed leftover temp folder: {folder}")
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to remove leftover temp folder {folder}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleanup complete. Removed {deleted_count} leftover folder(s).")
