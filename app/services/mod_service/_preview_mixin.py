# app/services/mod_service/_preview_mixin.py
"""Preview-image management: add, remove, remove-all, reorder, property update.

Extracted from the original monolithic ``mod_service.py`` per ADR 0001.
The Mixin must NOT define ``__init__``.
"""
import json
from pathlib import Path

from app.models.mod_item_model import FolderItem
from app.core.constants import (
    INFO_JSON_NAME,
    FOLDER_PREVIEW_PREFIX,
)
from app.services.persist_utils import find_game_root_from_folder
from app.utils.system_utils import SystemUtils
from app.utils.logger_utils import logger
import dataclasses


class _PreviewMixin:
    # --- Preview-image management and property updates ---

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

