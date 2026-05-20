# app/models/config_model.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, TYPE_CHECKING

# Use TYPE_CHECKING to avoid circular imports at runtime
if TYPE_CHECKING:
    from .game_model import Game


@dataclass(frozen=True)
class Preset:
    """Represents a single saved mod preset."""

    name: str
    type: str  # 'safe' or 'unsafe'
    enabled_mod_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AppConfig:
    """Holds the application's entire configuration state. Immutable."""

    games: list[Game] = field(default_factory=list)

    # --- Last Session State ---
    last_active_game_id: str | None = None
    last_active_object_id: str | None = None
    last_active_folder_id: str | None = None

    # --- Global Settings ---
    safe_mode_enabled: bool = False
    presets: dict[str, Preset] = field(default_factory=dict)
    launcher_path: str | None = None
    auto_play_on_startup: bool = False

    # --- UI Preferences ---
    window_geometry: tuple[int, int, int, int] | None = None
    splitter_sizes: tuple[int, int, int] | None = None
    description_editor_height: int | None = None
    object_list_view_mode: str = "list"
