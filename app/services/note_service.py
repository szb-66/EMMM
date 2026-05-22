"""Per-mod keybinding notes persistence via _emm_notes.json."""

import json
import tempfile
from pathlib import Path
from typing import Dict

from app.utils.logger_utils import logger

NOTES_FILE_NAME = "_emm_notes.json"


def _notes_path(mod_path: Path) -> Path:
    return mod_path / NOTES_FILE_NAME


class NoteService:
    """Read/write human-readable notes for keybindings in a mod's _emm_notes.json."""

    def load_notes(self, mod_path: Path) -> Dict[str, str]:
        """Load keybinding notes from _emm_notes.json in *mod_path*.

        Returns an empty dict when the file does not exist or cannot be parsed.
        """
        path = _notes_path(mod_path)
        if not path.is_file():
            return {}

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            notes = data.get("keybinding_notes", {})
            if not isinstance(notes, dict):
                logger.warning(
                    "_emm_notes.json: keybinding_notes is not a dict, resetting."
                )
                return {}
            return {k: str(v) for k, v in notes.items()}
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read %s: %s", path, e)
            return {}

    def save_notes(self, mod_path: Path, notes: Dict[str, str]) -> None:
        """Atomically write notes to _emm_notes.json.

        Filters out empty-string values to keep the file tidy.
        """
        path = _notes_path(mod_path)
        data = {
            "version": 1,
            "keybinding_notes": {k: v for k, v in notes.items() if v},
        }

        try:
            fd, tmp_path = tempfile.mkstemp(
                suffix=".tmp",
                prefix=NOTES_FILE_NAME,
                dir=path.parent,
            )
            try:
                with open(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                tmp_path.replace(path)
            except Exception:
                Path(tmp_path).unlink(missing_ok=True)
                raise
        except OSError as e:
            logger.error("Failed to save notes to %s: %s", path, e)
            raise

    def update_note(self, mod_path: Path, key: str, note: str) -> Dict[str, str]:
        """Set a single note and persist. Returns the full updated notes dict."""
        notes = self.load_notes(mod_path)
        if note:
            notes[key] = note
        else:
            notes.pop(key, None)
        self.save_notes(mod_path, notes)
        return notes
