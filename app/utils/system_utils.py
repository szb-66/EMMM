# app/utils/system_utils.py
import concurrent.futures
import os
import sys
import subprocess
import threading
from pathlib import Path
from send2trash import send2trash
from app.utils.logger_utils import logger
from app.core.signals import global_signals

_SEND2TRASH_TIMEOUT = 5  # seconds


class SystemUtils:
    """A collection of static utility functions for OS-level interactions."""

    @staticmethod
    def open_path_in_explorer(path: Path):
        """
        Flow 4.3: Opens a file or directory path in the default system file explorer.
        This function is cross-platform compatible.
        """
        if not path or not path.exists():
            error_msg = f"Path does not exist: {path}"
            logger.error(error_msg)
            global_signals.toast_requested.emit(error_msg, "error")
            return

        logger.info(f"Opening path: {path}")
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            error_msg = f"Failed to open path '{path}' in file explorer."
            logger.critical(f"{error_msg} Reason: {e}", exc_info=True)
            global_signals.toast_requested.emit(error_msg, "error")

    # Tracks paths that were permanently deleted via fallback (for caller notification)
    _fallback_deleted_paths: set = set()
    _fallback_lock: threading.Lock = threading.Lock()

    @staticmethod
    def move_to_recycle_bin(path: Path) -> bool:
        """
        Flow 4.2.B: Safely moves a file or folder to the system's recycle bin
        with a timeout. Falls back to permanent deletion (os.remove) on timeout
        or failure.

        Returns True if the file was successfully deleted (recycle bin or fallback).
        Returns False only if ALL deletion methods fail.

        If fallback was used, the path is recorded in _fallback_deleted_paths
        so callers can check with pop_fallback_warnings().
        """
        if not path.exists():
            return False

        # 1. Attempt send2trash with timeout via ThreadPoolExecutor
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(send2trash, str(path))
                future.result(timeout=_SEND2TRASH_TIMEOUT)
            return True
        except concurrent.futures.TimeoutError:
            logger.warning(
                "send2trash timed out after %ds for '%s'. Attempting fallback deletion.",
                _SEND2TRASH_TIMEOUT,
                path,
            )
        except Exception as e:
            logger.warning(
                "send2trash failed for '%s': %s. Attempting fallback deletion.", path, e
            )

        # 2. Fallback: permanent deletion via os.remove
        try:
            os.remove(path)
            logger.warning(
                "Fallback: permanently deleted '%s' (recycle bin unavailable).", path
            )
            with SystemUtils._fallback_lock:
                SystemUtils._fallback_deleted_paths.add(str(path))
            return True
        except OSError as e:
            logger.error("Fallback deletion also failed for '%s': %s", path, e)
            return False

    @staticmethod
    def pop_fallback_warnings() -> list[str]:
        """Returns and clears the set of paths that were permanently deleted via fallback."""
        with SystemUtils._fallback_lock:
            paths = list(SystemUtils._fallback_deleted_paths)
            SystemUtils._fallback_deleted_paths.clear()
        return paths

    @staticmethod
    def get_initial_name(name: str, length: int = 2) -> str:
        """Flow 4.2.A: Returns the first 'length' characters of a name."""
        # This is used to generate initials for items without thumbnails.
        if not name:
            return "No Image"
        return name[:length].upper()

    @staticmethod
    def generate_item_id(output_path: Path, parent_path: Path) -> str:
        """
        Flow 4.2.C: Generates a unique item ID based on the output path and parent path.
        This is used to ensure unique identifiers for items in the UI.
        """
        if not output_path or not parent_path:
            return "unknown_item"

        # Use relative path to generate a unique ID
        relative_path = output_path.relative_to(parent_path)
        item_id = relative_path.as_posix().replace("/", "_").replace("\\", "_")
        return item_id