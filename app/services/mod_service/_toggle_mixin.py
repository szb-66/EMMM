# app/services/mod_service/_toggle_mixin.py
"""Status toggle + runtime persistent-state snapshot/restore.

Extracted from the original monolithic ``mod_service.py`` per ADR 0001.
The Mixin must NOT define ``__init__``.
"""
import json
import os
from pathlib import Path

from app.models.mod_item_model import BaseModItem, ObjectItem, FolderItem, ModStatus
from app.core.constants import (
    PROPERTIES_JSON_NAME,
    INFO_JSON_NAME,
    DEFAULT_DISABLED_PREFIX,
    PIN_SUFFIX,
)
from app.services.persist_utils import (
    find_game_root_from_folder,
    normalize_persist_key,
    read_user_persist_values,
    strip_disabled_prefix,
    write_user_persist_values,
)
from app.utils.logger_utils import logger
import dataclasses


class _ToggleMixin:
    # --- Status toggle and persistent-state snapshot/restore ---

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

    def _metadata_path_for_item(self, item: BaseModItem) -> Path:
        filename = PROPERTIES_JSON_NAME if isinstance(item, ObjectItem) else INFO_JSON_NAME
        return item.folder_path / filename

    def _read_json_or_empty(self, json_path: Path) -> dict:
        if not json_path.is_file():
            return {}
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

