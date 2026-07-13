# Main.py
import sys
import faulthandler
from pathlib import Path
from PyQt6.QtCore import QThreadPool, Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication
from qfluentwidgets import SplashScreen, setTheme, Theme
from app.utils.logger_utils import logger, set_log_directory
from app.core.constants import APP_ICON_PATH
from app.utils.async_utils import Worker

# --- Global crash diagnostics -------------------------------------------------
# faulthandler dumps a Python traceback to stderr the moment a fatal error is
# raised *or* the interpreter segfaults, which is the only reliable signal for
# the native (Qt C++) crashes we see when toggling mods.
faulthandler.enable()

_prev_excepthook = sys.excepthook


def _emit_excepthook(exc_type, value, tb):
    try:
        logger.critical(
            f"UNHANDLED EXCEPTION: {value!r}",
            exc_info=(exc_type, value, tb),
        )
    except Exception:
        pass
    _prev_excepthook(exc_type, value, tb)


sys.excepthook = _emit_excepthook


def _patch_flowlayout_takeat():
    """
    Fix a PyQt6-compatibility bug in ``qfluentwidgets.FlowLayout.takeAt``.

    The upstream implementation returns the wrapped ``QWidget`` instead of the
    ``QLayoutItem`` that ``QLayout.takeAt()`` is contractually required to
    return. Under PyQt6's strict type checking any caller of ``takeAt`` raises
    ``TypeError: invalid result from FlowLayout.takeAt(), QWidget cannot be
    converted to PyQt6.QtWidgets.QLayoutItem`` — and the C++ side then
    hard-crashes (0xC0000409 stack-buffer-overrun) when the layout is asked
    to reflow while a managed child is being torn down. This is the actual
    root cause of the "toggling a mod crashes the app" reports.

    The patched version returns the ``QLayoutItem`` (which is what callers
    expect), and continues to tear down any 'flowAni' animation previously
    associated with it. ``takeAllWidgets`` is replaced in lockstep because it
    relied on the buggy ``widget`` return value.
    """
    try:
        from qfluentwidgets import FlowLayout
    except Exception as exc:  # pragma: no cover
        logger.warning(f"Skipping FlowLayout patch (import failed): {exc}")
        return

    def _patched_takeAt(self, index: int):
        items = getattr(self, "_items", None)
        if not items or not (0 <= index < len(items)):
            return None
        item = items[index]
        widget = None
        try:
            widget = item.widget()
        except Exception:
            widget = None
        if widget is not None:
            try:
                ani = widget.property("flowAni")
            except Exception:
                ani = None
            if ani is not None:
                anis = getattr(self, "_anis", None)
                if isinstance(anis, list):
                    try:
                        anis.remove(ani)
                    except ValueError:
                        pass
                ani_group = getattr(self, "_aniGroup", None)
                if ani_group is not None:
                    try:
                        ani_group.removeAnimation(ani)
                    except Exception:
                        pass
                try:
                    ani.deleteLater()
                except Exception:
                    pass
        return items.pop(index)

    def _patched_takeAllWidgets(self):
        items = list(getattr(self, "_items", []))
        for item in items:
            widget = None
            try:
                widget = item.widget()
            except Exception:
                widget = None
            if widget is not None:
                try:
                    widget.deleteLater()
                except Exception:
                    pass
        if hasattr(self, "_items"):
            self._items.clear()

    FlowLayout.takeAt = _patched_takeAt
    FlowLayout.takeAllWidgets = _patched_takeAllWidgets
    logger.debug("FlowLayout.takeAt() monkey-patched for PyQt6 safety.")


_patch_flowlayout_takeat()
# --- end crash diagnostics ---------------------------------------------------

# Import core constants
from app.core.constants import (
    APP_NAME,
    CACHE_DIR_NAME,
    CONFIG_FILE_NAME,
    SCHEMA_FILE_NAME,
    DEFAULT_ICONS,
    LOG_DIR_NAME,
    ORG_NAME,
    CONTEXT_FOLDERGRID,
    CONTEXT_OBJECTLIST,
)

# Import services
from app.services import (
    ConfigService,
    GameService,
    ModService,
    IniKeyParsingService,
    ThumbnailService,
    DatabaseService,
    WorkflowService,
    NoteService,
)

# Import utilities
from app.utils import SystemUtils, ImageUtils

# Import view models
from app.viewmodels import (
    MainWindowViewModel,
    ModListViewModel,
    PreviewPanelViewModel,
    SettingsViewModel,
)

# Import the main view
from app.views.main_window import MainWindow


def main():
    """The main entry point for the application."""

    # --- 1. Qt Application Setup ---
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationName(APP_NAME)
    app.setApplicationName("Enabled Model Mods Manager")
    setTheme(Theme.DARK)
    # Note: Logger will be initialized when first used after log_path is set

    # --- SPLASH SCREEN SETUP ---
    # 1. Create and configure the splash screen BEFORE heavy work.
    #    The splash screen doesn't need a real parent yet, it will float on top.
    app_icon = QIcon(APP_ICON_PATH)
    app.setWindowIcon(app_icon)
    splash_screen = SplashScreen(app.windowIcon(), None)  # Parent can be None
    splash_screen.setIconSize(QSize(128, 128))
    splash_screen.show()

    # 2. IMPORTANT: Process events to make sure the splash screen is drawn
    #    before we start the heavy initialization.
    app.processEvents()

    # ---2. Composition Root: Create and Wire All Dependencies ---
    try:
        if getattr(sys, 'frozen', False):
            # If the application is run as a bundle (e.g., by PyInstaller)
            application_path = Path(sys.executable).parent.resolve()
        else:
            # If running in a normal Python environment
            application_path = Path(__file__).parent.resolve()

        config_path = application_path / CONFIG_FILE_NAME
        cache_path = application_path / CACHE_DIR_NAME
        log_path = application_path / LOG_DIR_NAME
        schema_path = application_path / "app" / "assets" / SCHEMA_FILE_NAME


        # Ensure necessary directories exist
        cache_path.mkdir(parents=True, exist_ok=True)
        log_path.mkdir(parents=True, exist_ok=True)

        # Set the correct log directory before first logger usage
        set_log_directory(log_path)
        logger.info("Application starting with correct log path...")

        # ---Instantiate Services ---
        # Services with no or minimal dependencies first.
        config_service = ConfigService(config_path)
        # Apply saved language before any widget constructs (widgets call tr() in __init__).
        from app.core import i18n as _i18n
        _initial_cfg = config_service.load_config()
        _i18n.set_language(_initial_cfg.language)
        game_service = GameService()
        database_service = DatabaseService(schema_path=schema_path, app_path=application_path)
        ini_key_parsing_service = IniKeyParsingService()
        thumbnail_service = ThumbnailService(
            cache_dir=cache_path, default_icons=DEFAULT_ICONS
        )


        # Instantiate utility classes (can be passed as dependencies if needed).
        system_utils = SystemUtils()
        image_utils = ImageUtils()
        note_service = NoteService()

        # Services that depend on other services.
        mod_service = ModService(
            database_service=database_service,
            image_utils=image_utils,
            system_utils=system_utils,
            app_path= application_path,
        )

        workflow_service = WorkflowService(
            mod_service=mod_service, config_service=config_service, database_service=database_service
        )

        logger.info("Core services and utilities initialized.")
    except Exception as e:
        logger.critical(f"Failed to initialize core components: {e}", exc_info=True)
        splash_screen.finish()
        return 1

    # ---Instantiate ViewModels ---
    # Child ViewModels
    objectlist_vm = ModListViewModel(
        context=CONTEXT_OBJECTLIST,
        mod_service=mod_service,
        workflow_service=workflow_service,
        database_service=database_service,
        thumbnail_service=thumbnail_service,
        system_utils=system_utils,
    )

    foldergrid_vm = ModListViewModel(
        context=CONTEXT_FOLDERGRID,
        mod_service=mod_service,
        workflow_service=workflow_service,
        database_service=database_service,
        thumbnail_service=thumbnail_service,
        system_utils=system_utils,
    )
    preview_panel_vm = PreviewPanelViewModel(
        mod_service=mod_service,
        config_service=config_service,
        ini_parsing_service=ini_key_parsing_service,
        thumbnail_service=thumbnail_service,
        foldergrid_vm=foldergrid_vm,
        sys_utils=system_utils,
        image_utils=image_utils,
        note_service=note_service,
    )
    settings_vm = SettingsViewModel(
        config_service=config_service,
        game_service=game_service,
        workflow_service=workflow_service,
        database_service=database_service,
    )

    # Create the main orchestrator ViewModel, injecting all other components.
    main_window_vm = MainWindowViewModel(
        config_service=config_service,
        workflow_service=workflow_service,
        objectlist_vm=objectlist_vm,
        foldergrid_vm=foldergrid_vm,
        preview_panel_vm=preview_panel_vm,
    )


    # ---3. Instanate the main window ---
    try:
        window = MainWindow(
            main_view_model=main_window_vm, settings_view_model=settings_vm
        )
        window.show()
        logger.debug("Main Window shown.")
    except Exception as e:
        logger.critical(f"Failed to initialize or show Main Window: {e}", exc_info=True)
        return 1

    # --- Run cache cleanup in the background ---
    logger.info("Queueing thumbnail disk cache cleanup task...")
    cleanup_worker = Worker(thumbnail_service.cleanup_disk_cache)

    thread_pool = QThreadPool.globalInstance()
    if thread_pool:
        thread_pool.start(cleanup_worker)
    else:
        logger.critical("Could not get QThreadPool instance to run cache cleanup.")

    logger.info("Performing startup cleanup...")
    mod_service.cleanup_lingering_temp_folders()

    # --- HIDE SPLASH SCREEN ---
    splash_screen.finish()

    # Start Application Event Loop
    logger.info("Entering event loop...")
    try:
        exit_code = app.exec()
        logger.info(f"Application exiting with code {exit_code}")
    except Exception as e:
        logger.critical(
            f"Unhandled exception in application event loop: {e}", exc_info=True
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
