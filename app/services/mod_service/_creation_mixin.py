# app/services/mod_service/_creation_mixin.py
"""Object/foldergrid creation, manual object build, archive analysis & extraction.

Extracted from the original monolithic ``mod_service.py`` per ADR 0001.
The Mixin must NOT define ``__init__``.
"""
import json
import os
import uuid
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import List

from PyQt6.QtGui import QImage
from PIL import Image

from app.models.mod_item_model import (
    ObjectItem,
    FolderItem,
    ModStatus,
)
from app.core.constants import (
    PROPERTIES_JSON_NAME,
    INFO_JSON_NAME,
    DEFAULT_DISABLED_PREFIX,
)
from app.utils.logger_utils import logger
import patoolib


class _CreationMixin:
    # --- Object creation, archive analysis & extraction, startup cleanup ---

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
                # Probe for .ini WITHOUT extracting the whole archive.
                # Full extraction here used to block the worker thread for
                # large/password-protected archives and could crash the app.
                if not self._archive_has_ini(path):
                    has_ini_warning = True
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

    def create_mod_from_source(self, source_path: Path, output_name: str, parent_path: Path, cancel_flag: List[bool], password: str | None = None) -> dict:
        """
        [NEW] Creates a new mod folder by either copying a directory or
        extracting an archive. This operation is cancellable.

        Parameters
        ----------
        password : str | None
            Optional password forwarded to patoolib for encrypted archives.
            When provided and the backend cannot satisfy it, a
            ``password_required`` status is returned so the caller can
            prompt the user.
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
                    #    interactive=False keeps the worker thread from
                    #    blocking on a TTY prompt for missing passwords;
                    #    password kw (when provided) is forwarded to patoolib.
                    patoolib.extract_archive(
                        str(source_path),
                        outdir=str(temp_path),
                        verbosity=-1,
                        interactive=False,
                        password=password,
                    )

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

