# app/services/config_service.py
import json
from pathlib import Path
import configparser
from typing import Any
from app.models.config_model import AppConfig
from app.models.game_model import Game
from app.utils.logger_utils import logger


class ConfigSaveError(IOError):
    pass


class ConfigService:
    """Manages all read/write operations for the config.ini file."""

    def __init__(self, config_path: Path):
        # --- Service Setup ---
        self.config_path = config_path

    def load_config(self) -> AppConfig:
        """
        Flow 1.1: Loads the entire configuration from config.json.
        Handles FileNotFoundError and parsing errors gracefully by returning a default AppConfig.
        """
        if not self.config_path.exists():
            logger.warning(
                f"Config file not found at '{self.config_path}'. Returning default config."
            )
            return AppConfig()

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # --- Parse [games] list ---
            games_data = data.get("games", [])
            games = []
            for game_dict in games_data:
                try:
                    # Pastikan path adalah objek Path dan valid
                    game_path = Path(game_dict.get("path"))
                    if game_path.is_dir():
                        games.append(
                            Game(
                                id=game_dict.get("id"),
                                name=game_dict.get("name"),
                                path=game_path,
                                game_type=game_dict.get("game_type")
                            )
                        )
                    else:
                        logger.warning(
                            f"Path for game '{game_dict.get('name')}' does not exist: '{game_path}'. Skipping."
                        )
                except (TypeError, KeyError) as e:
                    logger.error(f"Malformed game entry in config.json: {game_dict}. Error: {e}. Skipping.")


            # --- Parse [settings] object ---
            settings = data.get("settings", {})
            last_active_game_id = settings.get("last_active_game_id")
            safe_mode_enabled = bool(settings.get("safe_mode_enabled", False))

            launcher_path = settings.get("launcher_path")
            auto_play_on_startup = bool(settings.get("auto_play_on_startup", False))

            # language preference (default to zh per user choice)
            from app.core import i18n as _i18n
            language = settings.get("language", _i18n.DEFAULT_LANGUAGE)
            if language not in _i18n.AVAILABLE_LANGUAGES:
                logger.warning(f"Unknown language '{language}' in config. Falling back to default.")
                language = _i18n.DEFAULT_LANGUAGE

            # --- Parse [ui] object ---
            ui_prefs = data.get("ui", {})
            geometry = tuple(ui_prefs.get("window_geometry")) if "window_geometry" in ui_prefs and ui_prefs.get("window_geometry") is not None else None
            splitter_sizes = tuple(ui_prefs.get("splitter_sizes")) if "splitter_sizes" in ui_prefs and ui_prefs.get("splitter_sizes") is not None else None
            description_editor_height = ui_prefs.get("description_editor_height")
            object_list_view_mode = ui_prefs.get("object_list_view_mode", "list")

            # Validate geometry and splitter_sizes
            if geometry and len(geometry) != 4:
                logger.warning(f"window_geometry has {len(geometry)} values, expected 4. Ignoring.")
                geometry = None
            if splitter_sizes and len(splitter_sizes) != 3:
                logger.warning(f"splitter_sizes has {len(splitter_sizes)} values, expected 3. Ignoring.")
                splitter_sizes = None
            if not isinstance(description_editor_height, int) or not (60 <= description_editor_height <= 320):
                if description_editor_height is not None:
                    logger.warning(
                        f"description_editor_height={description_editor_height} is invalid. Ignoring."
                    )
                description_editor_height = None
            if object_list_view_mode not in {"list", "card"}:
                logger.warning(
                    f"object_list_view_mode={object_list_view_mode!r} is invalid. Falling back to list."
                )
                object_list_view_mode = "list"

            logger.info("Successfully loaded configuration from config.json.")
            return AppConfig(
                games=games,
                last_active_game_id=last_active_game_id,
                safe_mode_enabled=safe_mode_enabled,
                launcher_path=launcher_path,
                auto_play_on_startup=auto_play_on_startup,
                window_geometry=geometry,
                splitter_sizes=splitter_sizes,
                description_editor_height=description_editor_height,
                object_list_view_mode=object_list_view_mode,
                language=language,
                # preset will be handled later
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse config.json: {e}. Returning default config.")
            return AppConfig()
        except Exception as e:
            logger.critical(f"An unexpected error occurred while loading config: {e}", exc_info=True)
            return AppConfig()

    def save_config(self, config: AppConfig):
        """
        [REVISED] Saves the entire AppConfig object to the config.json file.
        This operation serializes the dataclasses into a JSON structure.
        """
        logger.info(f"Saving configuration to {self.config_path}...")

        try:
            existing_ui = {}
            if self.config_path.exists():
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        existing_ui = json.load(f).get("ui", {})
                except (IOError, json.JSONDecodeError):
                    existing_ui = {}

            description_editor_height = (
                config.description_editor_height
                if config.description_editor_height is not None
                else existing_ui.get("description_editor_height")
            )
            object_list_view_mode = (
                config.object_list_view_mode
                if config.object_list_view_mode in {"list", "card"}
                else existing_ui.get("object_list_view_mode", "list")
            )

            # 1. Build the main dictionary from the AppConfig object
            config_data = {
                "settings": {
                    "last_active_game_id": config.last_active_game_id,
                    "safe_mode_enabled": config.safe_mode_enabled,
                    "launcher_path": config.launcher_path,
                    "auto_play_on_startup": config.auto_play_on_startup,
                    "language": config.language,
                },
                "ui": {
                    "window_geometry": config.window_geometry,
                    "splitter_sizes": config.splitter_sizes,
                    "description_editor_height": description_editor_height,
                    "object_list_view_mode": object_list_view_mode,
                },
                "games": [
                    {
                        "id": game.id,
                        "name": game.name,
                        "path": str(game.path),  # Convert Path object to string for JSON
                        "game_type": game.game_type,
                    }
                    for game in config.games
                ],
                "presets": {
                    # Logic for presets will be added here in the future
                },
            }

            # 2. Write the dictionary to the JSON file
            with open(self.config_path, "w", encoding="utf-8") as f:
                # Use indent=4 for a human-readable file
                json.dump(config_data, f, indent=4)

            logger.info("Configuration saved successfully to config.json.")

        except IOError as e:
            # Raise a custom error to be caught by the ViewModel
            logger.error(f"IOError while saving config: {e}", exc_info=True)
            raise ConfigSaveError(f"Failed to write to config file: {e}") from e
        except TypeError as e:
            # This can happen if a data type is not JSON serializable
            logger.error(f"TypeError during JSON serialization: {e}", exc_info=True)
            raise ConfigSaveError(f"A data type could not be saved to JSON: {e}") from e

    def save_setting(self, key: str, value: Any, section: str = "settings"):
        """
        [REVISED] Saves a single key-value pair to the config.json file.
        This operation reads the entire file, updates one value, and writes it back.
        """
        # Ensure section key is lowercase to match our structure
        section = section.lower()

        try:
            # 1. Read the entire existing config file
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            else:
                # If the file doesn't exist, start with an empty structure
                config_data = {"settings": {}, "ui": {}, "games": [], "presets": {}}

            # 2. Update the value in the dictionary
            # Ensure the section dictionary exists
            if section not in config_data:
                config_data[section] = {}

            config_data[section][key] = value

            # 3. Write the entire dictionary back to the file
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=4)

            logger.info(f"Saved setting: [{section}] {key} = {value}")

        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Failed to save setting '{key}' to config file: {e}")
            # Optionally raise an error or handle it silently
            raise ConfigSaveError(f"Failed to update setting '{key}': {e}") from e
