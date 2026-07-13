from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QSizePolicy,
    QWidget,
    QSplitter,
    QHBoxLayout,
    QVBoxLayout,
    QFrame,
    QStyle
)
from app.utils.logger_utils import logger
from qfluentwidgets import (
    FluentWindow,
    InfoBar,
    InfoBarPosition,
    StrongBodyLabel,
    TitleLabel,
    ComboBox,
    SwitchButton,
    PushButton,
    FluentIcon,
    Flyout,
    ProgressBar,
    FlyoutAnimationType
)

# Import ViewModels
from app.utils.ui_utils import UiUtils
from app.core import i18n as _i18n
from app.viewmodels.main_window_vm import MainWindowViewModel
from app.viewmodels.settings_vm import SettingsViewModel

# Import Custom Panels (Views)

from app.views.sections.objectlist_panel import ObjectListPanel
from app.views.sections.foldergrid_panel import FolderGridPanel
from app.views.sections.preview_panel import PreviewPanel


# Import Dialogs (Views)
from app.views.dialogs.edit_game_dialog import EditGameDialog
from app.views.dialogs.settings_dialog import SettingsDialog


class MainWindow(FluentWindow):
    """The main application window. It receives fully constructed ViewModels."""

    def __init__(
        self,
        main_view_model: MainWindowViewModel,
        settings_view_model: SettingsViewModel,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.progress_bar_info = None
        # Store the injected ViewModels
        self.main_window_vm = main_view_model
        self.settings_vm = settings_view_model

        # ---Initialize UI and connect signals ---
        self._init_ui()
        self._bind_view_models()

        # Flow 1.1: Trigger the initial data loading sequence after setup.
        self.main_window_vm.start_initial_load()


    def _init_ui(self) -> None:
        """
        Builds the window layout using FluentWindow's managed navigation system.
        This version correctly integrates a filter sidebar with the main content area.
        """
        # ---------- 1. Window Basic Setup ----------
        self.setWindowTitle("EMM - Mods Manager")
        self.resize(1440, 760)
        self.setMinimumSize(960, 600)

        # ---------- 2. Create the Main Content Widget ----------
        # This widget will contain everything EXCEPT the new sidebar:
        # the header, splitter, and all three panels.
        central_widget = QWidget()
        content_v_layout = QVBoxLayout(central_widget)
        content_v_layout.setContentsMargins(0, 0, 0, 0)
        content_v_layout.setSpacing(0)

        # ---------- 3. Build Header and Panels (sama seperti kode asli Anda) ----------
        # Header
        self.header_widget = QWidget()
        hl = QHBoxLayout(self.header_widget)
        hl.setContentsMargins(12, 6, 12, 6)
        hl.setSpacing(10)
        # ... (semua kode untuk membuat gamelist_combo, buttons, dll. tetap sama)
        # Left Group
        left = QHBoxLayout()
        left.setSpacing(10)
        self.gamelist_combo = ComboBox()
        self.gamelist_combo.setPlaceholderText(_i18n.tr("main.select_game"))
        self.gamelist_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.safe_mode_switch = SwitchButton(_i18n.tr("main.safe_mode"))
        self.safe_mode_switch.setVisible(False)  # Hide for now, can be enabled later
        left.addWidget(self.gamelist_combo)
        left.addWidget(self.safe_mode_switch)
        left.addStretch(1)
        # Right Group
        right = QHBoxLayout()
        right.setSpacing(6)
        self.refresh_button = PushButton(FluentIcon.SYNC, _i18n.tr("main.refresh"))
        self.settings_button = PushButton(FluentIcon.SETTING, _i18n.tr("main.settings"))
        self.play_button = PushButton(FluentIcon.PLAY, _i18n.tr("main.play"))
        self.play_button.setEnabled(False)
        right.addWidget(self.refresh_button)
        right.addWidget(self.settings_button)
        right.addWidget(self.play_button)
        hl.addLayout(left)
        hl.addLayout(right)

        # Panels
        self.object_list_panel = ObjectListPanel(self.main_window_vm.objectlist_vm, self)
        self.folder_grid_panel = FolderGridPanel(self.main_window_vm.foldergrid_vm, self)
        self.preview_panel = PreviewPanel(self.main_window_vm.preview_panel_vm, self)
        self.object_list_panel.setMinimumWidth(284)
        self.object_list_panel.setMaximumWidth(400)
        self.preview_panel.setMinimumWidth(276)

        # Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(4)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.object_list_panel)
        self.splitter.addWidget(self.folder_grid_panel)
        self.splitter.addWidget(self.preview_panel)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([300, 600, 300])

        # Assemble the content widget
        content_v_layout.addWidget(self.header_widget)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        content_v_layout.addWidget(line)
        content_v_layout.addWidget(self.splitter, 1)

        # ---------- 4. Register Content and Add Sidebar Filters ----------
        # This is the crucial part. We treat the entire content area as one "page"
        # and then add our filter items to the same navigation panel.

        # Add the main content area as a "sub-interface". It doesn't need an icon
        # because our filter items will control it. We give it a unique routeKey.
        central_widget.setObjectName("main_content_view")
        main_content_nav_item = self.addSubInterface(central_widget, FluentIcon.HOME, "Main Content")
        main_content_nav_item.setVisible(False)

        # Add a separator to the sidebar
        self.navigationInterface.addSeparator()

        # Add our filter items. These don't switch pages; they call the ViewModel.
        self.navigationInterface.addItem(
            routeKey='character_filter',  # Unique key for the navigation item
            icon=FluentIcon.PEOPLE,
            text=_i18n.tr("main.character"),
            onClick=lambda: self.main_window_vm.on_category_selected('character')
        )
        self.navigationInterface.addItem(
            routeKey='other_filter',  # Unique key
            icon=FluentIcon.APPLICATION,
            text=_i18n.tr("main.other"),
            onClick=lambda: self.main_window_vm.on_category_selected('other')
        )

        # Set the default selected item in the sidebar
        self.navigationInterface.setCurrentItem('character_filter')

    def _bind_view_models(self):
        """Connects signals and slots between this main view and its viewmodels."""
        # ---Connect ViewModel Signals to MainWindow Slots (VM -> View) ---
        self.main_window_vm.game_list_updated.connect(self._on_game_list_updated)
        self.main_window_vm.active_game_changed.connect(self._on_active_game_changed)
        self.main_window_vm.toast_requested.connect(self._on_toast_requested)
        self.main_window_vm.objectlist_vm.bulk_operation_started.connect(self._on_bulk_operation_started)
        self.main_window_vm.bulk_progress_updated.connect(self._on_bulk_progress_updated)
        self.main_window_vm.objectlist_vm.bulk_operation_finished.connect(self._on_bulk_operation_finished)
        self.main_window_vm.objectlist_vm.game_type_setup_required.connect(self._on_game_type_setup_required)
        self.main_window_vm.category_switch_requested.connect(self._on_category_switch_requested)
        self.play_button.clicked.connect(self.main_window_vm.on_play_button_clicked)
        self.main_window_vm.play_settings_required.connect(self._on_play_settings_required)
        self.main_window_vm.play_button_state_changed.connect(self.play_button.setEnabled)

        self.main_window_vm.settings_dialog_requested.connect(
            self._on_settings_dialog_requested
        )
        # ---Connect MainWindow UI Actions to ViewModel Slots (View -> VM) ---
        self.gamelist_combo.currentIndexChanged.connect(self._on_game_selection_changed)
        # self.safe_mode_switch.toggled.connect(self.main_window_vm.toggle_safe_mode)
        self.refresh_button.clicked.connect(self.main_window_vm.request_main_refresh)
        self.settings_button.clicked.connect(self._on_settings_dialog_requested)

        # ---Connect Child Panel Signals for Orchestration ---
        # When the item on the left panel is clicked, call the method in main_window_vm
        self.object_list_panel.item_selected.connect(
            self.main_window_vm.set_active_object
        )

        # When the item in the panel is clicked, immediately update preview_panel_vm
        self.folder_grid_panel.item_selected.connect(
            self.main_window_vm.preview_panel_vm.set_current_item
        )
        self.main_window_vm.preview_panel_vm.unsaved_changes_prompt_requested.connect(
            self._on_preview_unsaved_changes
        )

    def _on_toast_requested(self, message: str, level: str = "info"):
        """
        Creates and shows a non-blocking InfoBar (toast) notification
        at the top-right of the window.
        """
        # Determine the title and InfoBar creation method based on the level
        if level == "success":
            title = _i18n.tr("toast.success")
            InfoBar.success(
                title=title,
                content=message,
                duration=2000,
                parent=self,
                position=InfoBarPosition.BOTTOM_RIGHT,  # Add this line
            )
        elif level == "warning":
            title = _i18n.tr("toast.warning")
            InfoBar.warning(
                title=title,
                content=message,
                duration=3000,
                parent=self,
                position=InfoBarPosition.BOTTOM_RIGHT,  # Add this line
            )
        elif level == "error":
            title = _i18n.tr("toast.error")
            InfoBar.error(
                title=title,
                content=message,
                duration=4000,
                parent=self,
                position=InfoBarPosition.BOTTOM_RIGHT,  # Add this line
            )
        else:  # Default to "info"
            title = _i18n.tr("toast.info")
            InfoBar.info(
                title=title,
                content=message,
                duration=2000,
                parent=self,
                position=InfoBarPosition.BOTTOM_RIGHT,  # Add this line
            )

    def _on_game_selection_changed(self, index: int):
        """
        Handles user selecting a new game from the combobox.
        """
        # Guard clause: Do nothing if the index is invalid (e.g., when clearing the list)
        if index < 0:
            return

        game_name = self.gamelist_combo.itemText(index)

        # Guard clause: Do nothing if selection is invalid or hasn't actually changed
        if not game_name or (
            self.main_window_vm.active_game
            and self.main_window_vm.active_game.name == game_name
        ):
            return

        logger.info(f"User selected new game from dropdown: '{game_name}'")
        self.main_window_vm.set_current_game_by_name(game_name)

    def _on_game_list_updated(self, games_data: list[dict]):
        """Flow 2.1 Step 3: Updates the game list combobox with new data."""
        self.gamelist_combo.blockSignals(True)
        self.gamelist_combo.clear()

        if games_data:
            self.gamelist_combo.addItems([game["name"] for game in games_data])
            self.gamelist_combo.setEnabled(True)
        else:
            self.gamelist_combo.setEnabled(False)
            self.gamelist_combo.setPlaceholderText(_i18n.tr("main.no_games"))

        self.gamelist_combo.blockSignals(False)

        # After updating the list, ensure the current selection is correct
        if self.main_window_vm.active_game:
            active_game_data = {
                "name": self.main_window_vm.active_game.name,
                "id": self.main_window_vm.active_game.id,
            }
            self._on_active_game_changed(active_game_data)
        else:
            self._on_active_game_changed(None)

    def _on_active_game_changed(self, game_data: dict | None):
        """Flow 2.1 Step 4: Syncs the UI when the active game changes."""
        self.gamelist_combo.blockSignals(True)
        if game_data:
            self.gamelist_combo.setCurrentText(game_data["name"])
            self.play_button.setEnabled(True)
        else:
            # If no game is active, clear selection and disable play button
            self.gamelist_combo.setCurrentIndex(-1)
            self.play_button.setEnabled(False)
        self.gamelist_combo.blockSignals(False)

    def _on_settings_dialog_requested(self, initial_tab: str = "games_tab"):
        """Flow 1.2: Creates and shows the SettingsDialog."""
        logger.info("Settings dialog requested.")

        # 1. Check if the main_window_vm has a valid config.
        if self.main_window_vm.config is None:
            logger.warning("No config available to load into SettingsDialog.")
            return

        # 2. Create the dialog instance, passing the ViewModel
        dialog = SettingsDialog(viewmodel=self.settings_vm, parent=self)
        dialog.view_model.reconciliation_finished.connect(
            self.main_window_vm.request_main_refresh
        )
        # 3. Load the current config into the dialog's ViewModel
        self.settings_vm.load_current_config(self.main_window_vm.config)
        dialog._switch_to_tab(initial_tab)

        # 4. Execute the dialog and check the result
        if dialog.exec():
            # This block runs only if the user clicks "Save" AND
            # the save operation in the ViewModel is successful.
            logger.info("Settings saved. Refreshing main window state.")
            self.main_window_vm.refresh_all_from_config()

        pass

    def _on_game_type_setup_required(self, game_id: str):
        """
        Handles the request from the ViewModel to force the user to set a game_type
        for a misconfigured game.
        """
        logger.warning(f"UI received request to configure game_type for game ID: {game_id}")

        current_config = self.main_window_vm.config
        if not current_config:
            logger.error("Cannot handle game_type setup: main config is not loaded.")
            return
        self.settings_vm.load_current_config(current_config)

        # 1. Get the full game data from the *main* config, which is the source of truth
        game_data = next((g for g in current_config.games if g.id == game_id), None)
        if not game_data:
            logger.error(f"Could not find game with ID {game_id} to configure.")
            return


        # 2. Get available types from the database to populate the ComboBox
        db_service = self.main_window_vm.objectlist_vm.database_service
        available_types = db_service.get_all_game_types()

        # 3. Create and show the EditGameDialog in 'force selection' mode
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

        # Center the dialog
        dialog.move(
            self.geometry().center() - dialog.rect().center()
        )

        if dialog.exec():
            # 4. If the user saves, update and save the configuration immediately
            updated_data = dialog.get_data()

            # update the ViewModel with the new game data
            self.settings_vm.update_temp_game(
                game_id=updated_data["id"],
                new_name=updated_data["name"],
                new_path=updated_data["path"],
                new_game_type=updated_data["game_type"]
            )

            # save the changes to the main config
            if self.settings_vm.save_all_changes():
                logger.info(f"Game '{updated_data['name']}' successfully updated with a new game_type.")
                # Reload the main config to sync the entire application
                self.main_window_vm.refresh_all_from_config()

                UiUtils.show_toast(
                    self,
                    _i18n.tr("main.game_config_updated"),
                    "success"
                )

            else:
                logger.error("Failed to save the updated game configuration after forced setup.")

    def _on_preview_unsaved_changes(self, context: dict):
        """
        Flow 5.2 Part A: Prompts the user to confirm discarding unsaved changes.
        """
        title = _i18n.tr("main.unsaved_title")
        content = _i18n.tr("main.unsaved_text")
        yes_text = _i18n.tr("main.unsaved_discard")
        cancel_text = _i18n.tr("common.cancel")

        if UiUtils.show_confirm_dialog(self, title, content, yes_text, cancel_text):
            next_item_data = context.get("next_item_data")
            self.main_window_vm.preview_panel_vm.discard_changes_and_proceed(
                next_item_data
            )
            return


    def _on_bulk_operation_started(self, message: str = ""):
        """Disables interactions and shows a progress indicator."""
        # Disable all interactive elements to prevent user actions during bulk operations
        self.object_list_panel.setEnabled(False)
        self.folder_grid_panel.setEnabled(False)
        self.preview_panel.setEnabled(False)
        if self.progress_bar_info:
            self.progress_bar_info.close()

        # Create and show the new progress bar
        self.progress_bar_info = self._create_progress_bar()
        self.progress_bar_info.show()
        # ---------------------

    def _on_bulk_operation_finished(self, failed_items: list):
        """Re-enables interactions and hides the progress indicator."""

        # 1. Disconnect the progress signal to prevent any late-arriving updates.
        try:
            self.main_window_vm.bulk_progress_updated.disconnect(self._on_bulk_progress_updated)
        except TypeError:
            # This can happen if the signal was already disconnected. It's safe to ignore.
            pass

        # self.navigation_interface.setEnabled(True)
        self.object_list_panel.setEnabled(True)
        self.folder_grid_panel.setEnabled(True)
        self.preview_panel.setEnabled(True)
        if self.progress_bar_info:
            self.progress_bar_info.close()
            self.progress_bar_info = None

        # refresh request_main_refresh
        self.main_window_vm.request_main_refresh()

        if failed_items:
            error_message = _i18n.tr("main.bulk_errors", count=len(failed_items))
            UiUtils.show_toast(self, error_message, "error")
            logger.error(error_message)

    def _on_bulk_progress_updated(self, current: int, total: int):
        """[REVISED] Updates the progress bar inside the flyout."""
        if self.progress_bar_info:
            if total > 0:
                percentage = int((current / total) * 100)
                self.progress_bar_info.titleLabel.setText(_i18n.tr("main.synchronizing", percent=percentage))
                if hasattr(self.progress_bar_info, 'progressBar'):
                    self.progress_bar_info.progressBar.setValue(percentage)

    def _create_progress_bar(self) -> InfoBar:
        """
        [NEW] Helper method to create a custom InfoBar with a progress bar.
        """
        # Create a container for the progress bar and title
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setContentsMargins(0, 8, 0, 8)

        titleLabel = StrongBodyLabel(_i18n.tr("main.synchronizing", percent=0), view)
        progressBar = ProgressBar(view)
        progressBar.setRange(0, 100)
        progressBar.setValue(0)

        layout.addWidget(titleLabel)
        layout.addWidget(progressBar)

        # Create an InfoBar instance that is not closable by the user
        bar = InfoBar(
            icon=FluentIcon.SYNC,
            title="", # Title will be inside our custom widget
            content="",
            isClosable=False, # User cannot close it manually
            duration=-1,      # Stays open until we close it
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self
        )
        # Add our custom widget to the InfoBar
        bar.addWidget(view)

        # Store a reference to the progress bar for easy access
        bar.progressBar = progressBar

        return bar

    def _on_category_switch_requested(self, category_key: str):
        """Switches the main sidebar to the specified category."""
        self.main_window_vm.on_category_selected(category_key)

        route_key = f"{category_key}_filter"
        logger.info(f"Programmatically switching sidebar to '{route_key}'")
        self.navigationInterface.setCurrentItem(route_key)

    def _on_play_settings_required(self):
        """
        Shows a toast notification and opens the SettingsDialog to the
        Launcher tab when the launcher path is not configured.
        """
        UiUtils.show_toast(
            self,
            _i18n.tr("main.launcher_not_set"),
            "info",
            duration=3000
        )
        # Panggil metode yang sudah ada, tetapi dengan argumen tambahan
        self._on_settings_dialog_requested(initial_tab="launcher_tab")

    def closeEvent(self, event):
        self.main_window_vm.shutdown()
        super().closeEvent(event)
        pass
