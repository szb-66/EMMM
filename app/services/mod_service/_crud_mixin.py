# app/services/mod_service/_crud_mixin.py
"""Pin toggle, rename, delete, type conversion, DB sync, object update.

Extracted from the original monolithic ``mod_service.py`` per ADR 0001.
The Mixin must NOT define ``__init__``.
"""
import json
import os
import time
from pathlib import Path

from PyQt6.QtGui import QImage
from PIL import Image

from app.models.mod_item_model import (
    BaseModItem,
    ObjectItem,
    FolderItem,
    ModType,
    ModStatus,
)
from app.core.constants import (
    PROPERTIES_JSON_NAME,
    INFO_JSON_NAME,
    DEFAULT_DISABLED_PREFIX,
    PIN_SUFFIX,
)
from app.utils.logger_utils import logger
import dataclasses
import shutil
import uuid


class _CrudMixin:
    # --- Pin, rename, delete, type conversion, DB sync, object update ---

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
            # Build the updated in-memory model so callers can do a
            # targeted UI update instead of a full directory rescan.
            update_fields = {"folder_path": current_path, "actual_name": new_name}
            if "object_type" in update_data:
                update_fields["object_type"] = ModType(update_data["object_type"])
            if "rarity" in update_data:
                update_fields["rarity"] = update_data["rarity"]
            if "element" in update_data:
                update_fields["element"] = update_data["element"]
            if "gender" in update_data:
                update_fields["gender"] = update_data["gender"]
            if "weapon" in update_data:
                update_fields["weapon"] = update_data["weapon"]
            if "subtype" in update_data:
                update_fields["subtype"] = update_data["subtype"]
            if "tags" in update_data:
                update_fields["tags"] = update_data["tags"]
            if "thumbnail_path" in properties:
                thumb = properties["thumbnail_path"]
                update_fields["thumbnail_path"] = (
                    current_path / thumb if thumb else None
                )
            updated_item = dataclasses.replace(item, **update_fields)
            return {"success": True, "item_id": item.id, "data": updated_item}

        except Exception as e:
            error_msg = f"Failed to update object '{item.actual_name}': {e}"
            logger.error(error_msg, exc_info=True)
            # Attempt to roll back rename if it happened
            if needs_rename and current_path.exists() and not original_path.exists():
                os.rename(current_path, original_path)
            return {"success": False, "error": error_msg, "item_id": item.id}

