# App/views/sections/foldergrid panel.py


from pathlib import Path
from typing import Dict
from app.utils.logger_utils import logger
from PyQt6.QtCore import pyqtSignal, Qt, QUrl
from app.views.dialogs.confirmation_list_dialog import ConfirmationListDialog
from PyQt6.QtWidgets import (
    QFileDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
)
from PyQt6.QtGui import QAction
from qfluentwidgets import (
    FluentIcon,
    SearchLineEdit,
    DropDownToolButton,
    TransparentToolButton,
    PrimaryToolButton,
    ComboBox,
    ScrollArea,
    BodyLabel,
    PopUpAniStackedWidget,
    RoundMenu,
    PrimaryPushButton,
    PushButton,
    CheckBox,
    FlowLayout,
    TitleLabel,
    MessageBox,
    IconWidget,
    DropDownPushButton,
    PrimaryDropDownPushButton,
    Action
)
from qfluentwidgets.components.widgets import HorizontalSeparator
from app.viewmodels.mod_list_vm import ModListViewModel
from app.views.components.breadcrumb_widget import BreadcrumbWidget
from app.views.components.common.shimmer_frame import ShimmerFrame
from app.views.components.common.flow_grid_widget import FlowGridWidget
from app.views.components.foldergrid_widget import FolderGridItemWidget
from app.views.dialogs.failure_report_dialog import FailureReportDialog
from app.views.dialogs.password_dialog import PasswordDialog
from app.views.dialogs.progress_dialog import ProgressDialog


class FolderGridPanel(QWidget):
    """The UI panel that displays the grid of mod folders and subfolders."""

    # Custom signal to notify the main window that a new item is selected for preview

    item_selected = pyqtSignal(object)

    def __init__(self, viewmodel: ModListViewModel, parent: QWidget | None = None):
        super().__init__(parent)
        self.view_model = viewmodel
        self._item_widgets: Dict[str, QWidget] = {}  # Maps item_id to its widget

        self.filter_menu = None
        self.filter_widgets = {}

        self._init_ui()
        self._bind_viewmodel()

        # Enable Drag & Drop for this panel

        self.setAcceptDrops(True)

    # In app/views/sections/foldergrid_panel.py

    def _init_ui(self):
        """Initializes all UI components for this panel (Fluent-enhanced)."""

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 10, 0, 5)
        main_layout.setSpacing(6)

        self.setLayout(main_layout)

        # ---Toolbar ---
        toolbar = QHBoxLayout(self)
        toolbar.setSpacing(6)
        toolbar.setContentsMargins(14, 1, 14, 1)

        # Search
        self.search_bar = SearchLineEdit(self)
        self.search_bar.setPlaceholderText("Search folder…")
        toolbar.addWidget(self.search_bar)

        # Filter dropdown
        self.filter_btn = DropDownToolButton(FluentIcon.FILTER, self)
        self.filter_btn.setToolTip("Filter")
        self.filter_menu = RoundMenu(parent=self)
        self.filter_btn.setMenu(self.filter_menu)
        toolbar.addWidget(self.filter_btn)

        # Preset combo
        self.preset_combo = ComboBox(self)
        self.preset_combo.setPlaceholderText("Apply Preset")
        self.preset_combo.setMinimumWidth(150)
        self.preset_combo.setEnabled(False)
        toolbar.addWidget(self.preset_combo)
        self.preset_combo.setVisible(False)  # Hide for now, can be enabled later

        # Shuffle button
        self.randomize_btn = TransparentToolButton(FluentIcon.ROTATE, self)
        self.randomize_btn.setToolTip("Shuffle mods")
        toolbar.addWidget(self.randomize_btn)
        self.randomize_btn.setVisible(False)  # Hide for now, can be enabled later

        # Spacer
        toolbar.addStretch()

        # Create Button (Primary, on the far right)
        self.create_btn = PrimaryDropDownPushButton(FluentIcon.ADD, "Create Mod", self)
        self.create_btn.setToolTip("Create a new mod from archives or a folder")

        # Create a menu for the button
        create_menu = RoundMenu(parent=self.create_btn)
        create_menu.addAction(Action(FluentIcon.ZIP_FOLDER, "Add from Archives...",  triggered=lambda:self._on_add_archives_requested()))
        create_menu.addAction(Action(FluentIcon.FOLDER, "Add from Folder...", triggered=lambda:self._on_add_folder_requested()))
        self.create_btn.setMenu(create_menu)

        toolbar.addWidget(self.create_btn)

        main_layout.addLayout(toolbar)

        # --- Result Bar ---
        self.result_bar_widget = QWidget(self)
        self.result_bar_widget.setObjectName("ResultBar")
        result_bar_layout = QHBoxLayout(self.result_bar_widget)
        result_bar_layout.setContentsMargins(14, 4, 10, 4)
        self.result_label = BodyLabel("...")
        self.clear_filter_button = TransparentToolButton(FluentIcon.CLOSE, self.result_bar_widget)
        self.clear_filter_button.setToolTip("Clear all filters and search")
        result_bar_layout.addWidget(self.result_label, 1)
        result_bar_layout.addWidget(self.clear_filter_button)
        self.result_bar_widget.setVisible(False)
        main_layout.addWidget(self.result_bar_widget)

        # Breadcrumb & separator
        self.breadcrumb_widget = BreadcrumbWidget(self)
        main_layout.addWidget(self.breadcrumb_widget)
        separator = HorizontalSeparator(self)
        main_layout.addWidget(separator)

        # Stacked content area
        self.stack = PopUpAniStackedWidget(self)
        self.scroll_area = ScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        # Grid in scroll area
        self.grid_widget = FlowGridWidget(self)
        self.scroll_area.setWidget(self.grid_widget)

        # Placeholder, empty, loading states
        self.placeholder_label = BodyLabel("Select an object to view mods...", self)
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)


        # Widget for empty state
        self.empty_state_widget = QWidget(self)
        empty_layout = QVBoxLayout(self.empty_state_widget)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(10)
        self.empty_icon = IconWidget(FluentIcon.SEARCH, self.empty_state_widget)
        self.empty_icon.setFixedSize(48, 48)
        self.empty_title_label = TitleLabel("Title", self.empty_state_widget)
        self.empty_subtitle_label = BodyLabel("Subtitle", self.empty_state_widget)
        self.empty_subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_subtitle_label.setWordWrap(True)
        empty_layout.addStretch(1)
        empty_layout.addWidget(self.empty_icon, 0, Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_title_label, 0, Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_subtitle_label, 0, Qt.AlignmentFlag.AlignTop)
        empty_layout.addStretch(1)

        self.shimmer_frame = ShimmerFrame(self)

        # Add to the stack
        self.stack.addWidget(self.placeholder_label)
        self.stack.addWidget(self.scroll_area)
        self.stack.addWidget(self.empty_state_widget)
        self.stack.addWidget(self.shimmer_frame)

        main_layout.addWidget(self.stack, 1)

        # Set initial state
        self.stack.setCurrentWidget(self.placeholder_label)

    def _bind_viewmodel(self):
        """Connects this panel's widgets and slots to the ViewModel."""
        # ---Connect ViewModel signals to this panel's slots ---
        self.view_model.loading_started.connect(self._on_loading_started)
        self.view_model.loading_finished.connect(self._on_loading_finished)
        self.view_model.path_changed.connect(self._on_path_changed)
        self.view_model.items_updated.connect(self._on_items_updated)
        self.view_model.item_needs_update.connect(self._on_item_needs_update)
        self.view_model.item_processing_started.connect(
            self._on_item_processing_started
        )
        self.view_model.item_processing_finished.connect(
            self._on_item_processing_finished
        )
        self.view_model.selection_changed.connect(self._on_selection_changed)
        self.view_model.bulk_operation_started.connect(self._on_bulk_action_started)
        self.view_model.bulk_operation_finished.connect(self._on_bulk_action_completed)
        self.view_model.failure_report_requested.connect(self._on_failure_report_requested)

        # --- Connections for UI feedback ---
        self.view_model.exclusive_activation_confirmation_requested.connect(
            self._on_exclusive_activation_confirmation_requested
        )
        self.view_model.password_requested.connect(self._on_password_requested)
        self.view_model.filter_state_changed.connect(self._on_filter_state_changed)
        self.view_model.empty_state_changed.connect(self._on_empty_state_changed)
        self.view_model.clear_search_text.connect(self.search_bar.clear)
        self.clear_filter_button.clicked.connect(self.view_model.clear_all_filters_and_search)

        self.view_model.available_filters_changed.connect(self._on_available_filters_changed)

        # ---Connect UI widget actions to ViewModel slots ---
        self.view_model.active_selection_changed.connect(
            self._on_active_selection_changed
        )
        self.breadcrumb_widget.navigation_requested.connect(
            self._on_breadcrumb_navigation
        )
        self.search_bar.textChanged.connect(self.view_model.on_search_query_changed)

        self.view_model.creation_tasks_prepared.connect(self._on_creation_tasks_prepared)
        # self.randomize_button.clicked.connect(self.view_model.initiate_randomize)
        # (Connections for filter button, bulk action buttons, preset combobox, etc.)

    # ---SLOTS (Responding to ViewModel Signals) ---

    def _on_loading_started(self):
        """Flow 2.3: Clears the view and shows the loading shimmer."""
        self.grid_widget.clear_items()
        self._item_widgets.clear()
        self.stack.setCurrentWidget(self.shimmer_frame)

    def _on_loading_finished(self):
        """Flow 2.3: Hides the loading shimmer."""
        self.shimmer_frame.stop_shimmer()
        pass

    def _on_path_changed(self, new_path: Path | None):
        """Flow 2.3: Updates the breadcrumb widget with the new navigation path."""
        if new_path and new_path.is_dir():
            # The new breadcrumb widget handles all root path and update logic internally.
            # We just need to give it the current path.
            self.breadcrumb_widget.set_current_path(new_path)
            self.breadcrumb_widget.setVisible(True)
        else:
            # If path is None or invalid, clear and hide the breadcrumb.
            self.breadcrumb_widget.clear()
            self.breadcrumb_widget.setVisible(False)

            # The rest of your logic to show a placeholder is correct
            self.grid_widget.clear_items()
            self.stack.setCurrentWidget(self.placeholder_label)

    def _on_items_updated(self, items_data: list[dict], item_id_to_select: str | None = None):
        """
        Flow 2.3: Updates the grid view by reusing existing widgets when possible.
        Only creates/destroys widgets for items that were added/removed.
        """
        logger.debug(f"Received {len(items_data)} items to display in foldergrid.")

        # --- compute diff sets ---
        new_ids = {item["id"] for item in items_data}
        old_ids = set(self._item_widgets.keys())
        removed_ids = old_ids - new_ids
        kept_ids = old_ids & new_ids

        # --- detach all widgets from layout (they survive) ---
        self.grid_widget.clear_items()

        # --- destroy stale widgets ---
        for rid in removed_ids:
            widget = self._item_widgets.pop(rid, None)
            if widget:
                widget.deleteLater()

        # --- show appropriate view ---
        if not items_data:
            self._item_widgets.clear()
            return

        self.stack.setCurrentWidget(self.scroll_area)

        item_to_select_data = None

        for item_data in items_data:
            item_id = item_data["id"]

            if item_id in kept_ids:
                # Reuse existing widget, update its data
                widget = self._item_widgets[item_id]
                widget.set_data(item_data)
            else:
                # Create new widget for added item
                widget = FolderGridItemWidget(
                    item_data=item_data,
                    viewmodel=self.view_model,
                )
                widget.item_selected.connect(self._on_grid_item_selected)
                widget.item_selected.connect(self.item_selected)
                self._item_widgets[item_id] = widget

            self.grid_widget.add_widget(widget)

            if item_id_to_select is not None and item_id == item_id_to_select:
                item_to_select_data = item_data

        # Auto-select the intended item (triggers preview panel update)
        if item_to_select_data is not None:
            self._on_grid_item_selected(item_to_select_data)

    def _on_item_needs_update(self, item_data: dict):
        """Flow 2.3 Stage 2: Finds and redraws a single widget with hydrated data."""
        item_id = item_data.get("id") or ""
        # _item_widgets bisa berisi QListWidgetItem atau QWidget langsung
        # Bergantung pada implementasi panel Anda (QListWidget vs FlowLayout)
        list_or_item_widget = self._item_widgets.get(item_id)

        if not list_or_item_widget:
            return

        # Tentukan widget sebenarnya
        # Untuk ObjectListPanel (menggunakan QListWidget)
        widget = list_or_item_widget

        # Panggil set_data pada widget anak dengan data baru
        if isinstance(widget, FolderGridItemWidget):
            widget.set_data(item_data)

    def _on_item_processing_started(self, item_id: str):
        """Flow 3.1b & 4.2: Shows a processing state on a specific widget."""
        widget = self._item_widgets.get(item_id)
        if isinstance(widget, FolderGridItemWidget):
            widget.show_processing_state(True)

    def _on_item_processing_finished(self, item_id: str, success: bool):
        """Flow 3.1b & 4.2: Hides the processing state on a specific widget."""
        widget = self._item_widgets.get(item_id)
        if isinstance(widget, FolderGridItemWidget):
            widget.show_processing_state(False)

    # In app/views/sections/foldergrid_panel.py

    def _on_breadcrumb_navigation(self, path: Path):
        """
        Handles the navigation request from the breadcrumb widget.
        This slot ensures all necessary arguments are passed to the ViewModel.
        """
        logger.info(f"Breadcrumb navigation requested for path: {path}")

        # Get the current game context from the ViewModel
        current_game = self.view_model.current_game
        if not current_game:
            logger.error(
                "Cannot navigate via breadcrumb without an active game context."
            )
            return

        # Call the ViewModel's load_items method with all arguments complete
        self.view_model.load_items(
            path=path,
            game=current_game,
            is_new_root=False,  # Breadcrumb navigation is always within the current root
        )

    def _on_active_selection_changed(self, selected_item_id: str | None):
        """Applies a visual 'selected' state to the correct widget."""
        for item_id, widget in self._item_widgets.items():
            # You need to implement a 'set_selected' method on your widget
            # For example, it could change the border color or background.
            is_selected = item_id == selected_item_id

            if isinstance(widget, FolderGridItemWidget):
                widget.set_selected(is_selected)

    def _on_grid_item_selected(self, item_data: dict):
        """
        Handles when a grid item is single-clicked.
        Forwards selection to the main window AND tells the ViewModel about the new active selection.
        """
        # 1. Tell the ViewModel which item is now the active one
        item_id = item_data.get("id")
        self.view_model.set_active_selection(item_id)

        # 2. Forward the selection to the main window to update the preview panel
        self.item_selected.emit(item_data)

    def _on_available_filters_changed(self, filter_options: dict):
        """Clears and rebuilds the foldergrid filter menu UI controls dynamically."""
        self.filter_menu.clear()
        self.filter_widgets.clear()

        if not filter_options:
            action = QAction("No Filters Available", self)
            action.setEnabled(False)
            self.filter_menu.addAction(action)
            return

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Create filter controls dynamically
        for name, options in filter_options.items():
            layout.addWidget(BodyLabel(name))

            if name == 'Tags':
                # Use CheckBoxes for multi-select tags
                tags_widget = QWidget()
                tags_layout = FlowLayout(tags_widget) # Use FlowLayout for tags
                tags_layout.setContentsMargins(0, 0, 0, 0)
                tag_checkboxes = []
                for tag in options:
                    checkbox = CheckBox(tag)
                    tags_layout.addWidget(checkbox)
                    tag_checkboxes.append(checkbox)
                self.filter_widgets[name.lower()] = tag_checkboxes
                layout.addWidget(tags_widget)
            else: # For Author and other single-select filters
                combo = ComboBox()
                combo.addItems(["All"] + options)
                self.filter_widgets[name.lower()] = combo
                layout.addWidget(combo)

        layout.addSpacing(10)
        button_layout = QHBoxLayout()
        reset_button = PushButton("Reset")
        apply_button = PrimaryPushButton("Apply")
        button_layout.addWidget(reset_button)
        button_layout.addWidget(apply_button)
        layout.addLayout(button_layout)

        reset_button.clicked.connect(self._on_reset_filters)
        apply_button.clicked.connect(self._on_apply_filters)

        self.filter_menu.addWidget(container, selectable=False)

    def _on_apply_filters(self):
        """Collects filter values from all widgets and sends them to the ViewModel."""
        active_filters = {}
        for key, widget_or_list in self.filter_widgets.items():
            if isinstance(widget_or_list, list): # Handle CheckBoxes for Tags
                selected_tags = [cb.text() for cb in widget_or_list if cb.isChecked()]
                if selected_tags:
                    active_filters[key] = selected_tags
            elif isinstance(widget_or_list, ComboBox): # Handle ComboBox for Author
                value = widget_or_list.currentText()
                if value != "All":
                    active_filters[key] = value

        self.view_model.set_filters(active_filters)
        self.filter_menu.close()

    def _on_reset_filters(self):
        """Resets all filter widgets and tells the ViewModel to clear filters."""
        for key, widget_or_list in self.filter_widgets.items():
            if isinstance(widget_or_list, list):
                for cb in widget_or_list:
                    cb.setChecked(False)
            elif isinstance(widget_or_list, ComboBox):
                widget_or_list.setCurrentIndex(0)

        self.view_model.clear_filters()
        self.filter_menu.close()

    def _on_filter_state_changed(self, show_bar: bool, count: int):
        """Shows or hides the result bar based on the filter state."""
        if show_bar:
            plural = "s" if count > 1 else ""
            self.result_label.setText(f"{count} result{plural} found")

        self.result_bar_widget.setVisible(show_bar)

    def _on_empty_state_changed(self, title: str, subtitle: str):
        """Updates the text on the empty state widget and displays it."""
        self.empty_title_label.setText(title)
        self.empty_subtitle_label.setText(subtitle)

        if "filter" in subtitle or "criteria" in subtitle:
            self.empty_icon.setIcon(FluentIcon.FILTER)
        else:
            self.empty_icon.setIcon(FluentIcon.FOLDER)

        self.stack.setCurrentWidget(self.empty_state_widget)

    def _on_exclusive_activation_confirmation_requested(self, plan: dict):
        """
        [NEW] Receives the action plan from the ViewModel and shows a
        confirmation dialog to the user.
        """
        item_to_enable_name = plan.get("enable_name", "the selected mod")
        disable_names = plan.get("disable_names", [])

        # Build a clear and informative message for the user
        title = "Confirm Action"
        content = f"This will enable '{item_to_enable_name}'.\n\n"

        if disable_names:
            content += "The following currently active mod(s) will be disabled:\n"
            # List up to 5 mods to keep the dialog clean
            for name in disable_names[:5]:
                content += f"  • {name}\n"
            if len(disable_names) > 5:
                content += f"  • ...and {len(disable_names) - 5} more.\n"

        content += "\nDo you want to proceed?"

        # Create and show the confirmation dialog
        confirm_dialog = MessageBox(title, content, self.window())

        # The exec() method returns True if the user clicks the "Yes" button
        if confirm_dialog.exec():
            # If confirmed, call the ViewModel method to proceed with the action
            self.view_model.proceed_with_exclusive_activation(plan)


    def _on_selection_changed(self, has_selection: bool):
        """Flow 3.2: Enables or disables bulk action buttons based on selection."""
        # Self.bulk enable button.set enabled(has selection)

        pass

    def _on_bulk_action_started(self):
        """Flow 3.2 & 6.2: Disables UI controls during a bulk operation."""
        # Disable search, filter, create, randomize, presets, and all item checkboxes.

        pass

    def _on_bulk_action_completed(self, failed_items: list):
        """Flow 3.2 & 6.2: Re-enables UI controls after a bulk operation."""
        # Re-enable all controls disabled in the method above.

        pass

    def _on_failure_report_requested(self, failed_items: list):
        """
        [NEW] Creates and shows the FailureReportDialog with the list
        of items that failed during the operation.
        """
        if not failed_items:
            return

        dialog = FailureReportDialog(failed_items, self.window())
        dialog.exec()

    # ---UI EVENT HANDLERS (Forwarding to ViewModel) ---

    def contextMenuEvent(self, event):
        """Right-click on empty area: offers 'New Folder...' to create an empty folder."""
        if not self.view_model.current_path:
            super().contextMenuEvent(event)
            return

        menu = RoundMenu(parent=self)
        new_folder_action = QAction(FluentIcon.FOLDER_ADD.icon(), "New Folder...", self)
        new_folder_action.triggered.connect(self._on_new_folder_requested)
        menu.addAction(new_folder_action)
        menu.exec(event.globalPos())

    def _on_new_folder_requested(self):
        """Opens a RenameDialog to name the new folder, then delegates to the ViewModel."""
        from app.views.dialogs.rename_dialog import RenameDialog

        all_names = self.view_model.get_all_item_names()
        dialog = RenameDialog("New Folder", all_names, self.window())
        dialog.setWindowTitle("Create New Folder")
        dialog.ok_button.setText("Create")
        if dialog.exec():
            folder_name = dialog.get_new_name()
            self.view_model.create_new_folder(folder_name)

    def dragEnterEvent(self, event):
        """Accepts drags that contain local file paths."""
        try:
            urls = event.mimeData().urls()
            if not urls:
                event.ignore()
                return
            # Only accept the drag when at least one URL resolves to a real
            # local file path. Some virtual MIME sources (browser, special
            # folders) advertise hasUrls() but produce empty toLocalFile().
            if any(url.isLocalFile() and url.toLocalFile() for url in urls):
                event.acceptProposedAction()
            else:
                event.ignore()
        except Exception:
            # Swallow any unexpected MIME parsing errors so a malformed drag
            # never crashes the app.
            event.ignore()

    def dropEvent(self, event):
        """Handles dropped files/folders by sending their paths to the ViewModel."""
        try:
            paths = []
            for url in event.mimeData().urls():
                try:
                    local = url.toLocalFile()
                except Exception:
                    continue
                if not local:
                    continue
                p = Path(local)
                # Skip non-existent paths silently. An unsupported file (e.g.
                # a non-archive) will be reported by analyze_source_path as
                # "Unsupported file type." rather than crashing here.
                if not p.exists():
                    logger.warning(f"Skipping dropped non-existent path: {local}")
                    continue
                paths.append(p)

            if not paths:
                logger.warning("Drop discarded: no valid local paths in MIME data.")
                self.view_model.toast_requested.emit(
                    "Cannot drop: no valid files or folders detected.", "warning"
                )
                return

            logger.info(f"User dropped {len(paths)} item(s).")
            self.view_model.prepare_creation_tasks(paths)
        except Exception as e:
            logger.error(f"Unhandled error processing drop event: {e}", exc_info=True)
            self.view_model.toast_requested.emit(
                "Could not process dropped items. See logs for details.", "error"
            )

    def _on_add_archives_requested(self):
        """Opens a file dialog for multi-selection of archives."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Mod Archives",
            "", # Start directory
            "Archives (*.zip *.rar *.7z);;All files (*)"
        )
        if not file_paths:
            return

        paths = [Path(p) for p in file_paths]
        self.view_model.prepare_creation_tasks(paths)

    # Buat slot baru untuk memilih folder
    def _on_add_folder_requested(self):
        """Opens a directory dialog to select a single mod folder."""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Mod Folder",
            "" # Start directory
        )
        if not folder_path:
            return

        paths = [Path(folder_path)]
        self.view_model.prepare_creation_tasks(paths)

    def _on_creation_tasks_prepared(self, tasks: list):
        """
        [REVISED] Receives analyzed tasks, creates and shows the ProgressDialog,
        and then tells the ViewModel to start the background work.
        """
        if not tasks:
            logger.warning("Analysis resulted in no valid tasks to create.")
            return

        all_current_names = self.view_model.get_all_item_names()
        dialog = ConfirmationListDialog(tasks, all_current_names, self.window())

        if dialog.exec():
            final_tasks = dialog.get_final_tasks()
            logger.info(f"User confirmed creation of {len(final_tasks)} mods.")

            # 1. Create and show the ProgressDialog
            progress_dialog = ProgressDialog(self.window())

            # 2. Create cancel flag
            cancel_flag = [False]

            # 3. Connect the "Cancel" button in dialog to flag
            progress_dialog.cancel_requested.connect(lambda: cancel_flag.__setitem__(0, True))

            # 4. Call the new ViewModel method, pass the flags and signals
            self.view_model.start_background_creation(
                tasks=final_tasks,
                cancel_flag=cancel_flag,
                progress_signal=progress_dialog.update_progress,
                finished_signal=progress_dialog.close # Tutup dialog saat selesai
            )

            # 5. This will block until the background work is done
            progress_dialog.exec()

    def _on_password_requested(self, task: dict):
        """Shows a dialog to get the password for an encrypted archive."""
        archive_name = task['source_path'].name
        dialog = PasswordDialog(archive_name, self.window())

        if dialog.exec():
            password = dialog.get_password()
            self.view_model.retry_creation_with_password(task, password)
