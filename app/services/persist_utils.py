"""Shared persist-key utilities for 3DMigoto INI state persistence.

Consolidates logic duplicated between IniKeyParsingService and ModService
into standalone functions that both services delegate to.
"""

import re
from pathlib import Path

from app.core.constants import DISABLED_PREFIX_PATTERN
from app.utils.logger_utils import logger


def strip_disabled_prefix(value: str) -> str:
    """Remove a leading DISABLED_ prefix (any case) from *value*."""
    match = DISABLED_PREFIX_PATTERN.match(value)
    return value[match.end():] if match else value


def normalize_persist_key(key: str) -> str:
    """Normalize a persist key for comparison.

    - Replace / with \\
    - Strip DISABLED_ prefix from each path component
    - Lower-case everything
    """
    parts = [
        strip_disabled_prefix(part)
        for part in key.replace("/", "\\").split("\\")
    ]
    return "\\".join(parts).lower()


def find_game_root_from_folder(folder_path: Path) -> Path | None:
    """Walk up from *folder_path* looking for the game root directory.

    The game root is the first ancestor that contains *d3dx_user.ini* or
    *d3dx.ini*.  As a fallback, if an ancestor is named ``Mods`` its
    parent is returned.
    """
    for parent in folder_path.parents:
        if (parent / "d3dx_user.ini").is_file() or (parent / "d3dx.ini").is_file():
            return parent
        if parent.name.lower() == "mods":
            return parent.parent
    return None


def read_user_persist_values(user_config_path: Path | None) -> dict[str, str]:
    """Read ``$var = value`` lines from the ``[Constants]`` section.

    Returns a dict of **normalized** persist keys → current values.
    Returns an empty dict when the file does not exist or cannot be read.
    """
    if not user_config_path or not user_config_path.is_file():
        return {}

    values: dict[str, str] = {}
    in_constants = False
    line_regex = re.compile(r"\s*(\$.+?)\s*=\s*(.*)")
    try:
        for line in user_config_path.read_text(
            encoding="utf-8", errors="ignore"
        ).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(";") or stripped.startswith("#"):
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                in_constants = stripped[1:-1].lower() == "constants"
                continue
            if not in_constants:
                continue
            m = line_regex.match(stripped)
            if m:
                values[normalize_persist_key(m.group(1))] = m.group(2).strip()
    except Exception as e:
        logger.warning(
            "Could not read persistent state from %s: %s", user_config_path, e
        )
    return values


def write_user_persist_values(
    user_config_path: Path, values_to_write: dict[str, str]
) -> None:
    """Write *values_to_write* into the ``[Constants]`` section.

    *values_to_write* must use **normalized** persist keys (see
    :func:`normalize_persist_key`).  Existing values are updated in
    place; new entries are appended before the next section header.
    If the file does not exist a minimal ``[Constants]`` skeleton is
    created.
    """
    if user_config_path.exists():
        lines = user_config_path.read_text(
            encoding="utf-8", errors="ignore"
        ).splitlines(keepends=True)
    else:
        lines = [
            "; AUTOMATICALLY GENERATED FILE - DO NOT EDIT\n",
            ";\n",
            "; 3DMigoto will overwrite this file whenever persistent settings are altered.\n",
            ";\n",
            "[Constants]\n",
        ]

    written: set[str] = set()
    in_constants = False
    constants_seen = False
    inserted_before_next_section = False
    line_regex = re.compile(r"^(\s*)(\$.+?)(\s*=\s*)(.*?)(\r?\n?)$")

    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if constants_seen and in_constants and not inserted_before_next_section:
                _append_missing_persist_lines(new_lines, values_to_write, written)
                inserted_before_next_section = True
            in_constants = stripped[1:-1].lower() == "constants"
            constants_seen = constants_seen or in_constants
            new_lines.append(line)
            continue

        if in_constants:
            m = line_regex.match(line)
            if m:
                normalized_key = normalize_persist_key(m.group(2))
                if normalized_key in values_to_write:
                    new_lines.append(
                        f"{m.group(1)}{m.group(2)}{m.group(3)}"
                        f"{values_to_write[normalized_key]}{m.group(5)}"
                    )
                    written.add(normalized_key)
                    continue

        new_lines.append(line)

    if not constants_seen:
        new_lines.append("[Constants]\n")

    if not inserted_before_next_section:
        _append_missing_persist_lines(new_lines, values_to_write, written)

    user_config_path.write_text("".join(new_lines), encoding="utf-8")


def _append_missing_persist_lines(
    lines: list[str], values_to_write: dict[str, str], written: set[str]
) -> None:
    """Append any *values_to_write* entries not yet *written*."""
    if lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] = f"{lines[-1]}\n"
    for key, value in values_to_write.items():
        if key not in written:
            lines.append(f"{key} = {value}\n")
