# App/views/dialogs/settings dialog.py

from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QDialog,
    QStackedWidget,
    QTableWidgetItem,
    QFileDialog,
    QStyle,
    QFormLayout,
)
from qfluentwidgets import (
    Pivot,
    TableWidget,
    ListWidget,
    PrimaryPushButton,
    PushButton,
    FluentIcon,
    SubtitleLabel,
    Dialog,
    MessageBox,
    IconWidget,
    BodyLabel,
    TitleLabel,
    LineEdit,
    CheckBox,
    ComboBox,
)
from app.utils.ui_utils import UiUtils
from app.utils.logger_utils import logger
from app.core import i18n as _i18n
from app.viewmodels.settings_vm import SettingsViewModel
from app.views.dialogs.edit_game_dialog import EditGameDialog
from app.views.dialogs.select_game_type_dialog import SelectGameTypeDialog

class SettingsDialog(QDialog):  # Inherit from fluent Dialog
    """
    The main dialog for managing settings. It operates transactionally,
    only committing changes when the user explicitly saves.
    """

    def __init__(self, viewmodel: SettingsViewModel, parent: QWidget | None = None):
        super().__init__(parent)
        self.view_model = viewmodel
        self.pages = {}
        self._init_ui()
        self._connect_signals()  # To be implemented later

        self._refresh_all_lists()  # To be implemented later

    def _init_ui(self):
        """Initializes the UI components of the dialog."""
        self.setWindowTitle(_i18n.tr("settings.title"))
        self.setMinimumSize(700, 500)

        # REVISED: Create one main layout and apply it directly to the dialog
        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(15, 15, 15, 15)
        dialog_layout.setSpacing(10)

        # ---Pivot for Tab Navigation ---
        self.pivot = Pivot(self)

        # ---Stacked Widget for Tab Content ---
        self.stack = QStackedWidget(self)

        # ---Create and Add Tab Contents ---
        # Call these methods FIRST to populate the pivot and stack
        self._create_general_tab()
        self._create_games_tab()
        self._create_launcher_tab()
        self._create_presets_tab()

        # Set initial tab AFTER items have been added
        self.pivot.setCurrentItem("games_tab")

        # ---Assemble Layout ---

        dialog_layout.addWidget(self.pivot)
        dialog_layout.addWidget(
            self.stack, 1
        )  # The '1' makes the stack take available space

        # ---Bottom Buttons (Save/Cancel) ---

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)  # Push buttons to the right

        self.cancel_button = PushButton(_i18n.tr("common.cancel"))
        self.save_button = PrimaryPushButton(_i18n.tr("common.save"))
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.save_button)

        dialog_layout.addLayout(button_layout)

    def _create_general_tab(self):
        """Creates the UI for the 'General' settings tab (language picker)."""
        general_widget = QWidget()
        layout = QFormLayout(general_widget)
        layout.setContentsMargins(10, 20, 10, 10)
        layout.setSpacing(15)
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)

        self.language_combo = ComboBox(self)
        for code, label in _i18n.AVAILABLE_LANGUAGES.items():
            self.language_combo.addItem(label, userData=code)
        # Select current language
        current_lang = self.view_model.temp_language if hasattr(self.view_model, "temp_language") else _i18n.get_current_language()
        idx = self.language_combo.findData(current_lang)
        if idx >= 0:
            self.language_combo.setCurrentIndex(idx)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)

        layout.addRow(_i18n.tr("settings_general.language"), self.language_combo)
        layout.addRow("", BodyLabel(_i18n.tr("settings_general.language_hint"), self))

        self.pages["general_tab"] = general_widget
        self.stack.addWidget(general_widget)
        self.pivot.addItem(
            routeKey="general_tab",
            text=_i18n.tr("settings_general.title"),
            onClick=lambda: self._switch_to_tab("general_tab"),
            icon=FluentIcon.SETTING,
        )

    def _on_language_changed(self, _index: int):
        code = self.language_combo.currentData()
        if code:
            self.view_model.set_temp_language(code)

    def _create_games_tab(self):
        """Creates the UI for the 'Games' management tab."""
        games_widget = QWidget()
        layout = QVBoxLayout(games_widget)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        layout.addWidget(SubtitleLabel(_i18n.tr("settings.manage_paths")))

        toolbar_layout = QHBoxLayout()
        self.remove_game_button = PushButton(FluentIcon.DELETE, _i18n.tr("settings.remove_selected"))
        self.edit_game_button = PushButton(FluentIcon.EDIT, _i18n.tr("settings.edit_selected"))
        self.add_game_button = PushButton(FluentIcon.ADD, _i18n.tr("settings.add_game"))
        toolbar_layout.addWidget(self.remove_game_button)
        toolbar_layout.addWidget(self.edit_game_button)
        toolbar_layout.addWidget(self.add_game_button)
        toolbar_layout.addStretch(1)

        # Table to display games
        self.games_table = TableWidget(self)
        self.games_table.setColumnCount(3)
        self.games_table.setHorizontalHeaderLabels([_i18n.tr("settings.header_name"), _i18n.tr("settings.header_path"), _i18n.tr("settings.header_type")])
        self.games_table.setEditTriggers(self.games_table.EditTrigger.NoEditTriggers)

        # ---Apply fluent styles ---
        self.games_table.setBorderVisible(True)
        self.games_table.setBorderRadius(8)
        self.games_table.setSelectRightClickedRow(True)  # Good UX for context menus

        vertical_header = self.games_table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
        self.games_table.setWordWrap(False)
        self.games_table.setAlternatingRowColors(True)
        header = self.games_table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(1, header.ResizeMode.Stretch)
            header.setSectionResizeMode(2, header.ResizeMode.ResizeToContents)

        layout.addLayout(toolbar_layout)
        layout.addWidget(self.games_table, 1)

        self.pages["games_tab"] = games_widget

        self.stack.addWidget(games_widget)
        self.pivot.addItem(
            routeKey="games_tab",
            text=_i18n.tr("settings.manage_paths"),
            onClick=lambda: self._switch_to_tab("games_tab"),
            icon=FluentIcon.GAME,
        )

        sync_layout = QHBoxLayout()
        self.sync_game_button = PushButton(FluentIcon.SYNC, _i18n.tr("settings.sync_db"))
        self.sync_game_button.setToolTip(_i18n.tr("settings.sync_tooltip"))
        self.sync_game_button.setEnabled(False)
        sync_layout.addWidget(self.sync_game_button)
        sync_layout.addStretch(1)
        layout.addLayout(sync_layout)


    def _create_launcher_tab(self):
        """Creates the UI for the 'Launcher' settings tab."""
        launcher_widget = QWidget()
        layout = QFormLayout(launcher_widget)
        layout.setContentsMargins(10, 20, 10, 10)
        layout.setSpacing(15)
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)

        # -- Widget Launcher Path --
        path_layout = QHBoxLayout()
        self.launcher_path_edit = LineEdit(self)
        self.launcher_path_edit.setReadOnly(True)
        self.launcher_path_edit.setPlaceholderText(_i18n.tr("settings.no_launcher"))
        browse_button = PushButton(_i18n.tr("common.browse"))
        path_layout.addWidget(self.launcher_path_edit, 1)
        path_layout.addWidget(browse_button)

        layout.addRow(_i18n.tr("settings.launcher_path"), path_layout)

        # -- Widget Auto-play --
        self.auto_play_checkbox = CheckBox(_i18n.tr("settings.auto_play"), self)
        layout.addRow("", self.auto_play_checkbox)
        self.pages["launcher_tab"] = launcher_widget

        self.stack.addWidget(launcher_widget)
        self.pivot.addItem(
            routeKey="launcher_tab",
            text=_i18n.tr("settings_launcher.title"),
            onClick=lambda: self._switch_to_tab("launcher_tab"),
            icon=FluentIcon.PLAY_SOLID,
        )

        browse_button.clicked.connect(self._on_browse_launcher)
        self.auto_play_checkbox.toggled.connect(self.view_model.set_temp_auto_play)


    def _create_presets_tab(self):
        """Creates the UI for the 'Presets' management tab."""
        # This part of your code is also good

        presets_widget = QWidget()
        layout = QVBoxLayout(presets_widget)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        toolbar_layout = QHBoxLayout()
        self.rename_preset_button = PushButton(FluentIcon.EDIT, _i18n.tr("settings.rename_preset"))
        self.delete_preset_button = PushButton(FluentIcon.DELETE, _i18n.tr("settings.delete_preset"))
        toolbar_layout.addWidget(self.rename_preset_button)
        toolbar_layout.addWidget(self.delete_preset_button)
        toolbar_layout.addStretch(1)

        self.presets_list = ListWidget(self)
        self.presets_list.setObjectName("PresetsList")

        # Hide buttons and list until they are implemented
        self.rename_preset_button.setVisible(False)
        self.delete_preset_button.setVisible(False)
        self.presets_list.setVisible(False)

        # --- Widget "Coming Soon" ---
        layout.addStretch(1)

        coming_soon_icon = IconWidget(FluentIcon.DEVELOPER_TOOLS, presets_widget)
        coming_soon_icon.setFixedSize(48, 48)
        layout.addWidget(coming_soon_icon, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(5)

        title = TitleLabel(_i18n.tr("settings.coming_soon"), presets_widget)
        subtitle = BodyLabel(_i18n.tr("settings.presets_dev"), presets_widget)
        subtitle.setTextColor("#8a8a8a") # Warna abu-abu untuk subteks

        layout.addWidget(title, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addStretch(1)

        # -------------------------

        #layout.addWidget(SubtitleLabel("Manage Saved Presets"))
        #layout.addLayout(toolbar_layout)
        #layout.addWidget(self.presets_list, 1)
        self.pages["presets_tab"] = presets_widget
        self.stack.addWidget(presets_widget)
        self.pivot.addItem(
            routeKey="presets_tab",
            text=_i18n.tr("settings_presets.title"),
            onClick=lambda: self._switch_to_tab("presets_tab"),
            icon=FluentIcon.SAVE,
        )

    def _connect_signals(self):
        """Connects UI element signals and ViewModel signals to their handlers."""
        # ---ViewModel -> View ---
        self.games_table.itemSelectionChanged.connect(self._on_game_selection_changed)
        self.sync_game_button.clicked.connect(self._on_sync_this_game_clicked)
        self.view_model.bulk_operation_started.connect(self._on_long_op_started)
        self.view_model.bulk_operation_finished.connect(self._on_long_op_finished)


        self.view_model.games_list_refreshed.connect(self._refresh_game_list)
        self.view_model.toast_requested.connect(self._on_toast_requested)
        self.view_model.confirmation_requested.connect(self._on_confirmation_requested)
        self.view_model.error_dialog_requested.connect(self._on_error_dialog_requested)
        self.view_model.game_type_selection_requested.connect(self._on_game_type_selection_requested)
        # ---View -> ViewModel ---

        self.add_game_button.clicked.connect(self._on_add_game)
        self.edit_game_button.clicked.connect(self._on_edit_game)
        self.games_table.itemDoubleClicked.connect(self._on_edit_game)
        self.remove_game_button.clicked.connect(self._on_remove_game)
        self.view_model.launcher_settings_refreshed.connect(self._refresh_launcher_tab)
        # self.rename_preset_button.clicked.connect(self._on_rename_preset)
        # self.delete_preset_button.clicked.connect(self._on_delete_preset)

        # Connect Save and Cancel buttons
        self.save_button.clicked.connect(self._on_save)
        self.cancel_button.clicked.connect(self.reject)

    def _on_confirmation_requested(self, params: dict):
        """Membuat dan menampilkan dialog konfirmasi fluent."""
        title = params.get("title", "Confirmation")
        text = params.get("text", "")
        context = params.get("context", {})

        # Using dialogue from QFluentwidgets as in your reference
        if UiUtils.show_confirm_dialog(self, title, text, "Yes", "No"):
            # Users press "yes" or "ok"
            self.view_model.on_confirmation_result(True, context)
        else:
            # The user presses "no", "cancel", or closes dialogue
            self.view_model.on_confirmation_result(False, context)

    def _on_toast_requested(self, message: str, level: str):
        """Creates a non-blocking InfoBar notification inside the dialog."""
        # Call Master's Functions from Uiutils

        UiUtils.show_toast(
            parent=self,  # Toast will appear above this dialogue
            message=message,
            level=level,
        )

    # ---UI Refresh Methods ---

    def _refresh_all_lists(self):
        """A helper to refresh all lists in the dialog from the ViewModel's temp state."""
        view_data = [
            {"id": g.id, "name": g.name, "path": str(g.path)}
            for g in self.view_model.temp_games
        ]
        self._refresh_game_list(view_data)

    def _refresh_game_list(self, games_data: list[dict]):
        """Populates the game list view from the ViewModel's pre-formatted data."""
        logger.debug(f"Refreshing game list with {len(games_data)} items.")
        self.games_table.setRowCount(0)
        self.games_table.setRowCount(len(games_data))

        for row, game_dict in enumerate(games_data):
            # Use dictionary keys instead of object attributes

            name_item = QTableWidgetItem(game_dict["name"])
            path_item = QTableWidgetItem(game_dict["path"])
            game_type = game_dict.get("game_type") or "Not Set" # Tampilkan "Not Set" jika None
            type_item = QTableWidgetItem(game_type)

            # Store the game ID in the first item for easy retrieval

            name_item.setData(Qt.ItemDataRole.UserRole, game_dict["id"])
            self.games_table.setItem(row, 0, name_item)
            self.games_table.setItem(row, 1, path_item)
            self.games_table.setItem(row, 2, type_item)

        # Resize path column to fit content
        self.games_table.resizeColumnToContents(1)
        self.games_table.resizeColumnToContents(2)

    def _refresh_preset_list(self):
        """Populates the preset list view from the ViewModel's temp_presets."""
        pass

    # ---SLOTS (Responding to ViewModel Signals) ---

    def _on_sync_this_game_clicked(self):
        """
        [NEW] Handles the 'Sync Data with Database' button click.
        """
        selected_items = self.games_table.selectedItems()
        if not selected_items:
            UiUtils.show_toast(self, _i18n.tr("settings.please_select_sync"), "warning")
            return

        selected_row = selected_items[0].row()
        game_id = self.games_table.item(selected_row, 0).data(Qt.ItemDataRole.UserRole)
        game_name = self.games_table.item(selected_row, 0).text()

        # Show a confirmation dialog
        title = _i18n.tr("settings.confirm_full_sync_title")
        content = _i18n.tr("settings.confirm_full_sync_text", name=game_name)

        if UiUtils.show_confirm_dialog(self.window(), title, content, _i18n.tr("settings.yes_start_sync"), _i18n.tr("common.cancel")):
            # If confirmed, call the ViewModel to start the process
            self.view_model.initiate_reconciliation_for_game(game_id)

    def _on_long_op_started(self):
        """
        [REVISED] Shows an overlay on the dialog to prevent interaction
        during the sync process.
        """
        # self.overlay = ShimmerFrame(self)
        # self.overlay.setGeometry(self.rect())
        # self.overlay.start_shimmer()
        self.setEnabled(False)
        logger.info("Long operation started, dialog disabled.")


    def _on_long_op_finished(self):
        """
        [REVISED] Hides the overlay and re-enables the dialog.
        """
        # self.overlay.stop_shimmer()
        # self.overlay.hide()
        self.setEnabled(True)
        logger.info("Long operation finished, dialog enabled.")


    # ---UI EVENT HANDLERS (Calling ViewModel methods) ---
    def _on_add_game(self):
        """Flow 1.2: Membuka dialog folder dan meneruskannya ke ViewModel."""
        selected_path = QFileDialog.getExistingDirectory(
            self,
            _i18n.tr("settings.title"),
        )
        if selected_path:
            self.view_model.add_game_from_path(Path(selected_path))


    def _on_edit_game(self):
        """Flow 1.2: Opens an edit dialog for the selected game."""
        selected_items = self.games_table.selectedItems()

        if not selected_items:
            UiUtils.show_toast(self, _i18n.tr("settings.select_game_edit"), "warning")
            return

        selected_row = selected_items[0].row()
        game_id = self.games_table.item(selected_row, 0).data(Qt.ItemDataRole.UserRole)

        # Find the full game data from the viewmodel
        game_data = next((g for g in self.view_model.temp_games if g.id == game_id), None)
        if not game_data:
            return # Should not happen

        # Get available types from the database to populate the ComboBox
        available_types = self.view_model.database_service.get_all_game_types()

        # Convert dataclass to dict for the dialog
        game_dict = {
            "id": game_data.id,
            "name": game_data.name,
            "path": str(game_data.path),
            "game_type": game_data.game_type
        }

        dialog = EditGameDialog(game_data=game_dict, available_game_types=available_types, parent=self)
        if dialog.exec():
            updated_data = dialog.get_data()
            self.view_model.update_temp_game(
                game_id=updated_data["id"],
                new_name=updated_data["name"],
                new_path=updated_data["path"],
                new_game_type=updated_data["game_type"]
            )

    def _on_remove_game(self):
        """
        [IMPLEMENTED] Gets the selected game from the table, asks for confirmation,
        and tells the ViewModel to remove it from the temporary list.
        """
        # 1. Get the selected game from the table
        selected_items = self.games_table.selectedItems()
        if not selected_items:
            UiUtils.show_toast(self, _i18n.tr("settings.select_game_remove"), "warning")
            return

        selected_row = selected_items[0].row()
        game_id = self.games_table.item(selected_row, 0).data(Qt.ItemDataRole.UserRole)
        game_name = self.games_table.item(selected_row, 0).text()

        # 2. Show a confirmation dialog
        title = _i18n.tr("settings.confirm_removal_title")
        content = _i18n.tr("settings.confirm_removal_text", name=game_name)

        # We use a standard MessageBox here for confirmation
        confirm_dialog = MessageBox(title, content, self)

        if confirm_dialog.exec(): # This returns True if the user clicks 'Yes'
            # 3. If confirmed, call the ViewModel method
            self.view_model.remove_temp_game(game_id)

    def _on_rename_preset(self):
        """Flow 6.2.A: Opens a dialog to get a new name for a selected preset."""
        # 1. Get the selected preset.
        # 2. Open an input dialog to get the new name (with validation).
        # 3. Call self.view_model.rename_preset(old_name, new_name).

        pass

    def _on_delete_preset(self):
        """Flow 6.2.A: Confirms and tells the ViewModel to delete the selected preset."""
        # 1. Get the selected preset.
        # 2. Show a confirmation dialog.
        # 3. If confirmed, call self.view_model.delete_preset(preset_name).

        pass

    def _on_save(self):
        """Flow 1.2: Tells the ViewModel to commit all changes and closes the dialog on success."""
        for game in self.view_model.temp_games:
            if not game.game_type:
                # found a game without a game_type
                logger.warning(f"Save aborted: Game '{game.name}' is missing a game_type.")

                # Force the user to edit this game
                self._force_edit_game(game.id)

                # Stop the saving process
                return


        # If all games are valid, proceed with the saving process as usual
        if self.view_model.save_all_changes():
            self.accept()

    def _on_error_dialog_requested(self, title: str, message: str):
        """Shows a modal error dialog."""
        dialog = Dialog(title, message, self)
        dialog.exec()

    def _force_edit_game(self, game_id: str):
        """
        A helper method to trigger the edit dialog in force_selection_mode.
        This consolidates the logic from the previous step.
        """
        game_data = next((g for g in self.view_model.temp_games if g.id == game_id), None)
        if not game_data: return

        available_types = self.view_model.database_service.get_all_game_types()

        game_dict = {
            "id": game_data.id, "name": game_data.name,
            "path": str(game_data.path), "game_type": game_data.game_type
        }

        dialog = EditGameDialog(
            game_data=game_dict,
            available_game_types=available_types,
            parent=self,
            force_selection_mode=True
        )

        dialog.setGeometry(
            QStyle.alignedRect(Qt.LayoutDirection.LeftToRight, Qt.AlignmentFlag.AlignCenter, dialog.sizeHint(), self.geometry())
        )

        # --- Tampilkan dialog dan tunggu hasilnya ---
        if dialog.exec():
            # Jika pengguna mengklik "Save" di dialog edit
            updated_data = dialog.get_data()
            self.view_model.update_temp_game(
                game_id=updated_data["id"],
                new_name=updated_data["name"],
                new_path=updated_data["path"],
                new_game_type=updated_data["game_type"]
            )
            # Beri tahu pengguna untuk mencoba menyimpan lagi
            UiUtils.show_toast(self, _i18n.tr("settings.edit_then_save", name=updated_data['name']), "info")


    def _on_game_type_selection_requested(self, proposal: dict, available_types: list[str]):
        """
        Receives a signal from the ViewModel and shows a dialog to the user,
        asking them to manually select a game_type for a new game.
        """
        logger.info(f"UI received request to select game_type for '{proposal['name']}'.")

        dialog = SelectGameTypeDialog(
            proposal_name=proposal['name'],
            available_types=available_types,
            parent=self  # Parent is the SettingsDialog itself
        )

        # Center the dialog relative to the settings dialog
        dialog.setGeometry(
            QStyle.alignedRect(
                Qt.LayoutDirection.LeftToRight,
                Qt.AlignmentFlag.AlignCenter,
                dialog.sizeHint(),
                self.geometry(),
            )
        )

        if dialog.exec():
            # If user confirms, get the selection and send it back to the ViewModel
            selected_type = dialog.selected_game_type()
            self.view_model.set_game_type_and_add(proposal, selected_type)

    def _refresh_launcher_tab(self, launcher_path: str, auto_play: bool):
        """Populates the launcher tab UI from the ViewModel's state."""
        self.launcher_path_edit.setText(launcher_path)
        self.auto_play_checkbox.setChecked(auto_play)

    def _on_browse_launcher(self):
        """Opens a file dialog to select the launcher executable."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Launcher Executable",
            "", # Direktori awal
            "Executable files (*.exe);;All files (*)"
        )

        if file_path:
            # Perbarui tampilan UI
            self.launcher_path_edit.setText(file_path)
            # Beri tahu ViewModel tentang perubahan
            self.view_model.set_temp_launcher_path(file_path)

    def _switch_to_tab(self, routeKey: str):
        """
        A central method to handle tab switching. It updates both the
        QStackedWidget and the Pivot to ensure they are in sync.
        """
        target_widget = self.pages.get(routeKey)
        if target_widget:
            self.stack.setCurrentWidget(target_widget)
            self.pivot.setCurrentItem(routeKey)

    def _on_game_selection_changed(self):
        """
        [NEW] Enables or disables the 'Sync' and 'Edit'/'Remove' buttons
        based on whether a game is selected in the table.
        """
        is_a_game_selected = bool(self.games_table.selectedItems())

        self.sync_game_button.setEnabled(is_a_game_selected)
        self.edit_game_button.setEnabled(is_a_game_selected)
        self.remove_game_button.setEnabled(is_a_game_selected)