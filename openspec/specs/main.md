# EMMM - Enhanced Model Mods Manager

## Overview

EMMM is a desktop application for managing 3D model modifications (mods) for games using the XXMI/3DMigoto framework — specifically Genshin Impact (GIMI), Honkai: Star Rail (SRMI), Wuthering Waves (WWMI), and Zenless Zone Zero (ZZMI). Built with PyQt6 and Microsoft Fluent Design (via `qfluentwidgets`), it discovers and manages mod folders directly on the filesystem without imposing a rigid organizational structure.

## Tech Stack

- **Language:** Python 3.10+
- **GUI Framework:** PyQt6 (Qt 6.9)
- **UI Theming:** PyQt6-Fluent-Widgets >= 1.7.0
- **Image Processing:** Pillow 11.1.0
- **Filesystem Watching:** watchdog 6.0.0
- **Archive Extraction:** patoolib
- **Logging:** loguru 0.7.0
- **Recycle Bin:** send2trash 1.8.0

## Architecture

MVVM (Model-View-ViewModel) with a service layer, running on PyQt6's signal/slot mechanism for decoupled communication.

```
main.py  (composition root — wires all dependencies)
  │
  ├── Services (business logic, I/O, async workers)
  │   ├── ConfigService       — read/write config.json
  │   ├── GameService         — XXMI launcher detection, game discovery
  │   ├── ModService          — atomic filesystem operations (toggle, rename, delete, create)
  │   ├── DatabaseService     — load/query schema.json & game object databases
  │   ├── ThumbnailService    — generate, cache (L1 memory + L2 disk) thumbnails
  │   ├── IniKeyParsingService— parse & save 3DMigoto .ini keybindings
  │   ├── WorkflowService     — orchestrate multi-step/transactional workflows
  │   ├── FileWatcherService  — watchdog-based directory monitoring
  │   └── PersistUtils        — shared helpers for d3dx_user.ini persistence
  │
  ├── ViewModels (state & logic for each panel)
  │   ├── MainWindowViewModel       — top-level orchestrator, active game/object tracking
  │   ├── ModListViewModel          — manages objectlist & foldergrid item lists (×2 instances)
  │   ├── PreviewPanelViewModel     — selections, description, .ini editing, thumbnails
  │   └── SettingsViewModel         — game list, launcher, presets (transactional dialog state)
  │
  ├── Views (PyQt6 widgets)
  │   ├── MainWindow               — FluentWindow shell, header, splitter, sidebar filters
  │   ├── sections/
  │   │   ├── ObjectListPanel       — left panel: character/other object list
  │   │   ├── FolderGridPanel       — center panel: mod cards with breadcrumb & drag-drop
  │   │   └── PreviewPanel          — right panel: description, .ini editor, thumbnails
  │   ├── components/               — reusable widgets (thumbnail, breadcrumb, cards, etc.)
  │   └── dialogs/                  — settings, edit, create, progress, etc.
  │
  ├── Models (immutable dataclasses)
  │   ├── AppConfig    — full configuration state
  │   ├── Game         — single game entry
  │   ├── ObjectItem   — objectlist item (CharacterObjectItem / GenericObjectItem)
  │   ├── FolderItem   — foldergrid item (mod or navigable folder)
  │   └── Preset       — saved mod preset
  │
  └── Utils
      ├── SystemUtils   — OS operations (recycle bin, explorer, admin)
      ├── ImageUtils    — clipboard, compress, preview path generation
      ├── AsyncUtils    — Worker QRunnable, debounce
      ├── UiUtils       — toasts, confirm dialogs
      └── LoggerUtils   — loguru configuration
```

### Context separation

There are **two** `ModListViewModel` instances — one per context:
- `CONTEXT_OBJECTLIST` — the left panel showing top-level game items (characters, weapons, etc.)
- `CONTEXT_FOLDERGRID` — the center panel showing mod variants inside an object

Each instance shares the same class but adapts behavior based on `self.context`.

### Thread model

All I/O (disk scan, image processing, .ini parsing, archive extraction) runs off the main thread via `QThreadPool` + `Worker` (a `QRunnable` wrapper). Results are delivered back to the main thread through Qt signals.

### Data flow

1. **Startup:** `main.py` → creates Services → ViewModels → MainWindow → `start_initial_load()` → config loads asynchronously → `_process_config_update()` → `_determine_active_game()` → `set_current_game()` → `objectlist_vm.load_items()`
2. **Navigation:** select game → load objects → select object → load foldergrid → select mod → load preview + .ini
3. **Mutation:** UI action → ViewModel method → Worker (ModService) → signal result → ViewModel state update → signal → View UI refresh
4. **Domino effects:** Object toggle renames folder → `foldergrid_item_modified` → preview panel updates itself

### Key design decisions

- **Immutable models:** All model dataclasses are `frozen=True`. Updates produce new instances via `dataclasses.replace()`.
- **Skeleton pattern:** Items loaded in two passes — first fast "skeleton" (name, status, pin), then lazy "hydration" (metadata, thumbnails) when scrolled into view.
- **File-system-as-database:** Mod state (enabled/disabled, pinned) is encoded in the folder name itself (`DISABLED ` prefix, `_pin` suffix). JSON metadata files (`properties.json`, `info.json`) supplement with richer data.
- **Watcher suppression:** Internal file operations temporarily suppress the filesystem watcher to avoid redundant reloads.
- **Async I/O service:** `IniKeyParsingService.load_keybindings_async()` is the sole `asyncio` entry point (wrapped in `asyncio.run()` inside a worker).
