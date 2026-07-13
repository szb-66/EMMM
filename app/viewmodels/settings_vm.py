# App/viewmodels/settings vm.py

import dataclasses
from PyQt6.QtCore import QObject, pyqtSignal, QThreadPool
from pathlib import Path
from app.models.config_model import AppConfig
from app.models.game_model import Game
from app.services.config_service import ConfigService, ConfigSaveError
from app.services.game_service import GameService
from app.services.workflow_service import WorkflowService
from app.utils.async_utils import Worker
from app.utils.logger_utils import logger
from app.services.database_service import DatabaseService
from app.core import i18n as _i18n

class SettingsViewModel(QObject):
    """Manages the state and logic for the transactional Settings dialog."""

    # ---Signals for UI & Cross-ViewModel Communication ---

    games_list_refreshed = pyqtSignal(list)
    presets_list_refreshed = pyqtSignal(dict)
    config_updated = pyqtSignal()
    toast_requested = pyqtSignal(str, str)  # message, level
    game_type_selection_requested = pyqtSignal(dict, list)
    launcher_settings_refreshed = pyqtSignal(str, bool)  # launcher_path, auto_play
    confirmation_requested = pyqtSignal(dict)
    error_dialog_requested = pyqtSignal(str, str)  # title, message
    reconciliation_progress_updated = pyqtSignal(int, int) # current, total
    reconciliation_finished = pyqtSignal()
    bulk_operation_started = pyqtSignal()
    bulk_operation_finished = pyqtSignal(list)  # list of failed items

    def __init__(
        self,
        config_service: ConfigService,
        game_service: GameService,
        workflow_service: WorkflowService,
        database_service: DatabaseService,
    ):
        super().__init__()
        # ---Injected Services ---

        self.config_service = config_service
        self.game_service = game_service
        self.workflow_service = workflow_service
        self.database_service = database_service

        # ---Transactional State ---

        self.original_config: AppConfig | None = None
        self.temp_games: list[Game] = []  # A mutable list for game edits
        self.temp_launcher_path: str | None = None
        self.temp_auto_play: bool = False
        self.temp_language: str = _i18n.DEFAULT_LANGUAGE
        self.temp_presets: dict = {}  # A mutable dict for preset edits

    # ---Public Methods (API for the View) ---

    def load_current_config(self, app_config: AppConfig):
        """Flow 1.2: Loads current config into a temporary state for editing."""
        logger.info("Loading current configuration into SettingsViewModel.")
        self.original_config = app_config
        self.temp_games = list(app_config.games) if app_config else []
        self.temp_launcher_path = app_config.launcher_path
        self.temp_auto_play = app_config.auto_play_on_startup
        self.temp_language = app_config.language if app_config and app_config.language in _i18n.AVAILABLE_LANGUAGES else _i18n.DEFAULT_LANGUAGE
        # self.temp_presets = dict(app_config.presets) if app_config else {}

        # Prepare simple data for the view
        # Convert list[Game] to list[dict]
        view_data = [
            {"id": g.id, "name": g.name, "path": str(g.path), "game_type": g.game_type} for g in self.temp_games
        ]

        # Emit signals to tell the dialog to populate its UI
        self.games_list_refreshed.emit(view_data)
        self.launcher_settings_refreshed.emit(self.temp_launcher_path or "", self.temp_auto_play)

        # self.presets_list_refreshed.emit(self.temp_presets) # For later

    def save_all_changes(self) -> bool:
        """
        Validates temporary changes and saves them to disk via ConfigService.
        Returns True on success, False on failure.
        """
        logger.info("Attempting to save all settings changes.")
        # ---1. Final Validation ---

        names = [g.name for g in self.temp_games]
        if len(names) != len(set(names)):
            error_msg = _i18n.tr("settings.duplicate_names")
            logger.error(error_msg)
            self.error_dialog_requested.emit(_i18n.tr("settings.validation_error"), error_msg)
            return False

        # ---2. Create New Config State ---

        if not self.original_config:
            # Should not happen in normal flow, but as a safeguard

            new_config = AppConfig(
                games=self.temp_games,
                launcher_path=self.temp_launcher_path,
                auto_play_on_startup=self.temp_auto_play,
                language=self.temp_language,
            )
        else:
            new_config = dataclasses.replace(
                self.original_config,
                games=self.temp_games,
                launcher_path=self.temp_launcher_path,
                auto_play_on_startup=self.temp_auto_play,
                language=self.temp_language,
                # presets=self.temp_presets # Add this later
            )

        # ---3. Transactional Save ---
        try:
            self.config_service.save_config(new_config)
            self.config_updated.emit()  # Notify MainWindowViewModel

            if self.original_config and self.original_config.language != self.temp_language:
                self.toast_requested.emit(_i18n.tr("settings_general.saved_restart"), "info")

            return True
        except ConfigSaveError as e:
            logger.critical(f"Failed to save configuration: {e}", exc_info=True)
            self.error_dialog_requested.emit(
                _i18n.tr("settings.save_error"), _i18n.tr("settings.save_error_text", error=e)
            )
            return False

    # ---Game Management ---

    def add_game_from_path(self, path: Path):
        """Flow 1.2: Detects XXMI structure and proposes games from a given path."""
        detection_result = self.game_service.propose_games_from_path(path)

        if detection_result.suggested_launcher_path and not self.temp_launcher_path:
            logger.info(f"Auto-setting launcher path to suggested path: {detection_result.suggested_launcher_path}")
            self.set_temp_launcher_path(str(detection_result.suggested_launcher_path))
            self.launcher_settings_refreshed.emit(self.temp_launcher_path, self.temp_auto_play)

        if detection_result.is_detected:
            # Case 1: Multiple games found (XXMI structure)
            logger.info(f"XXMI structure detected at {path}.")
            dialog_params = {
                "title": _i18n.tr("settings.xxmi_detected"),
                "text": _i18n.tr("settings.xxmi_import_text", count=len(detection_result.proposals)),
                "context": {"proposals": detection_result.proposals}
            }
            self.confirmation_requested.emit(dialog_params)
        else:
            # Case 2: Single game found (fallback)
            # We still use the confirmation signal to keep the flow consistent.
            # The context is the same, so the handler doesn't need to change.
            game_name = detection_result.proposals[0].get('name', 'this folder')
            dialog_params = {
                "title": _i18n.tr("settings.confirm_new_game"),
                "text": _i18n.tr("settings.add_game_text", name=game_name),
                "context": {"proposals": detection_result.proposals}
            }
            self.confirmation_requested.emit(dialog_params)



    # Revised: a new slot to receive the results of the confirmation dialogue
    def on_confirmation_result(self, result: bool, context: dict):
        """Handles the result of the XXMI import confirmation."""
        proposals = context.get("proposals", [])
        if result:
            logger.info("User confirmed XXMI import. Processing all proposals.")
            self.process_individual_proposals(proposals)
        else:  # user cancelled
            self.toast_requested.emit(_i18n.tr("settings.import_cancelled"), "info")


    def process_individual_proposals(self, proposals: list[dict]):
        """
        Processes a list of proposals one by one, deciding whether to add
        directly or request a game_type from the user.
        """
        for proposal in proposals:
            # Check if the proposal is complete
            existing_paths = {str(g.path) for g in self.temp_games}
            existing_names = {g.name.lower() for g in self.temp_games}
            if proposal["name"].lower() in existing_names or str(proposal["path"]) in existing_paths:
                self.toast_requested.emit(_i18n.tr("settings.game_exists", name=proposal['name']), "warning")
                continue

            # If the proposal has a game_type, add it directly
            if proposal.get("game_type"):
                self.add_games_to_list([proposal])
            else:
                logger.info(f"Incomplete proposal for '{proposal['name']}'. Requesting user selection.")
                available_types = self.database_service.get_all_game_types()
                if available_types:
                    self.game_type_selection_requested.emit(proposal, available_types)
                else:
                    self.toast_requested.emit(_i18n.tr("settings.no_game_types_db"), "error")

    def set_game_type_and_add(self, proposal: dict, selected_game_type: str):
        """
        Called by the View after the user selects a game_type from the dialog.
        This method finalizes the proposal and adds it.
        """
        logger.info(f"User selected game_type '{selected_game_type}' for '{proposal['name']}'.")

        # Perbarui proposal dengan game_type yang dipilih pengguna
        proposal['game_type'] = selected_game_type

        # Kirim proposal yang sudah lengkap untuk diproses
        self.add_games_to_list([proposal])

    def add_games_to_list(self, proposals_to_add: list[dict]):
        """
        A helper method that takes a list of COMPLETE proposals and adds them
        to the temporary game list.
        """
        added_count = 0
        existing_paths = {str(g.path) for g in self.temp_games}
        existing_names = {g.name.lower() for g in self.temp_games}

        for proposal in proposals_to_add:
            name = proposal["name"]
            path_obj = proposal["path"]
            game_type = proposal.get("game_type")

            if name.lower() in existing_names or str(path_obj) in existing_paths:
                self.toast_requested.emit(_i18n.tr("settings.game_exists", name=name), "warning")
                continue

            logger.info(f"Adding new game to temporary list: {name} (Type: {game_type}) at {path_obj}")
            new_game = Game(name=name, path=path_obj, game_type=game_type)
            self.temp_games.append(new_game)
            added_count += 1

        if added_count > 0:
            # Refresh view
            view_data = [
                {"id": g.id, "name": g.name, "path": str(g.path), "game_type": g.game_type}
                for g in self.temp_games
            ]
            self.games_list_refreshed.emit(view_data)

    def update_temp_game(self, game_id: str, new_name: str, new_path: Path, new_game_type: str):
        """Flow 1.2: Edits a game in the temporary list."""
        # find the game to update by ID
        game_to_update = next((g for g in self.temp_games if g.id == game_id), None)
        if not game_to_update:
            logger.warning(f"Could not find game with ID {game_id} to update.")
            return

        # create a new Game object with updated values
        updated_game = Game(name=new_name, path=new_path, game_type=new_game_type, id=game_id)

        # Replace the old object with the new one in the list
        index = self.temp_games.index(game_to_update)
        self.temp_games[index] = updated_game

        logger.info(f"Updated game '{new_name}' in temporary list.")

        # Refresh view
        view_data = [
            {"id": g.id, "name": g.name, "path": str(g.path), "game_type": g.game_type}
            for g in self.temp_games
        ]
        self.games_list_refreshed.emit(view_data)

    def remove_temp_game(self, game_id: str):
        """
        [IMPLEMENTED] Removes a game from the temporary list based on its ID
        and emits a signal to refresh the view.
        """
        # Find the game to remove
        game_to_remove = next((g for g in self.temp_games if g.id == game_id), None)

        if not game_to_remove:
            logger.warning(f"Attempted to remove a game with ID '{game_id}' that does not exist.")
            self.toast_requested.emit("Could not find the selected game to remove.", "error")
            return

        # Remove the game from the list
        self.temp_games.remove(game_to_remove)
        logger.info(f"Removed game '{game_to_remove.name}' from temporary list.")

        # --- Refresh the view ---
        # Prepare the updated data for the view
        view_data = [
            {"id": g.id, "name": g.name, "path": str(g.path), "game_type": g.game_type}
            for g in self.temp_games
        ]
        # Emit the signal to tell the dialog to update its table
        self.games_list_refreshed.emit(view_data)

    # ---Preset Management (Async Operations) ---

    def set_temp_launcher_path(self, path: str):
        """Updates the temporary launcher path when the user changes it."""
        self.temp_launcher_path = path if path else None
        logger.debug(f"Temporary launcher path set to: {self.temp_launcher_path}")

    def set_temp_auto_play(self, is_checked: bool):
        """Updates the temporary auto-play state."""
        self.temp_auto_play = is_checked
        logger.debug(f"Temporary auto-play state set to: {self.temp_auto_play}")

    def set_temp_language(self, lang_code: str):
        """Updates the temporary language selection."""
        if lang_code in _i18n.AVAILABLE_LANGUAGES:
            self.temp_language = lang_code
            logger.debug(f"Temporary language set to: {self.temp_language}")

    def initiate_reconciliation_for_game(self, game_id: str):
        """
        [NEW] Starts the self-contained reconciliation workflow for a single game.
        """
        game_to_sync = next((g for g in self.temp_games if g.id == game_id), None)
        if not game_to_sync:
            self.toast_requested.emit(_i18n.tr("settings.game_to_sync_not_found", id=game_id), "error")
            return

        logger.info(f"User initiated reconciliation for game: '{game_to_sync.name}'")

        self.bulk_operation_started.emit()

        worker = Worker(
            self.workflow_service.reconcile_single_game,
            game_to_sync
        )

        worker.signals.progress.connect(self.reconciliation_progress_updated)
        worker.signals.error.connect(self._on_reconciliation_error)
        worker.signals.result.connect(self._on_reconciliation_finished)

        QThreadPool.globalInstance().start(worker)

    def _on_reconciliation_finished(self, result: dict):
        """
        [NEW] Handles the summary result from the single-game reconciliation workflow.
        """
        # Emit the bulk operation finished signal with any failures
        self.bulk_operation_finished.emit(result.get("failures", []))

        if result.get("created") or result.get("updated"):
            created = result.get("created", 0)
            updated = result.get("updated", 0)
            failed = result.get("failed", 0)

            game_type = result.get('game_type')
            if failed > 0:
                summary = _i18n.tr("settings.sync_with_failed", game_type=game_type, created=created, updated=updated, failed=failed)
                level = "warning"
            else:
                summary = _i18n.tr("settings.sync_complete", game_type=game_type, created=created, updated=updated)
                level = "success"
            self.toast_requested.emit(summary, level)

            # Beri tahu MainWindow bahwa ada perubahan dan ia perlu me-refresh
            self.reconciliation_finished.emit()
        elif result.get("error"):
            self.toast_requested.emit(_i18n.tr("vm.operation_failed", error=result.get('error')), "error")
        else:
            self.toast_requested.emit(_i18n.tr("settings.no_sync_changes"), "info")

    def _on_reconciliation_error(self, error_info: tuple):
        """
        [NEW] Handles a critical failure from the reconciliation worker.
        """
        exctype, value, tb = error_info
        logger.critical(f"A worker error occurred during reconciliation: {value}\n{tb}")

        self.bulk_operation_finished.emit([])
        self.toast_requested.emit(_i18n.tr("settings.sync_critical_error"), "error")

    def rename_preset(self, old_name: str, new_name: str):
        """Flow 6.2.A: Starts the async workflow to rename a preset and update all mods."""
        pass

    def delete_preset(self, preset_name: str):
        """Flow 6.2.A: Starts the async workflow to delete a preset and update all mods."""
        pass

    # ---Private Slots for Async Results ---

    def _on_preset_rename_finished(self, result: dict):
        """Handles the result of the preset rename workflow."""
        pass

    def _on_preset_delete_finished(self, result: dict):
        """Handles the result of the preset delete workflow."""
        pass
