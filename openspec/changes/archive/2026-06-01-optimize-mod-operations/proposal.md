## Why

Right-clicking a mod, adding preview images, and toggling mod status are noticeably laggy due to full UI rebuilds on every operation. External file system changes (e.g., deleting a mod folder in Explorer) are not reliably synchronized to the UI because the file watcher is non-recursive and internal suppression windows drop external events.

## What Changes

- **Incremental thumbnail gallery updates**: Adding or removing a single image no longer rebuilds the entire gallery widget set; only affected thumbnails are added/removed.
- **Persistent pixmap cache**: The in-memory pixmap cache survives item transitions so re-selecting a mod does not re-read images from disk.
- **INI parsing cache**: Parsed keybindings are cached per mod ID; switching back to a previously viewed mod skips re-parsing.
- **File watcher recursive mode**: Watchdog monitors subdirectory changes so deleting nested folders triggers a UI refresh.
- **Suppression window refinement**: External file system events are no longer silently dropped during the anti-flicker suppression window.
- **Toggle without full reload**: Toggling a mod's enable state updates the item in-place instead of triggering a full directory re-scan.

## Capabilities

### New Capabilities
- `thumbnail-gallery-performance`: Defines incremental gallery update behavior, persistent pixmap cache lifecycle, and lazy-loading strategy.

### Modified Capabilities
- `preview-gallery`: Add performance requirement specifying that gallery operations (add, remove, reorder) must not rebuild unaffected thumbnails.
- `services`: Add file watcher sync reliability requirement covering recursive monitoring and external event handling.

## Impact

- `app/views/components/thumbnail_widget.py` — `set_image_paths` → incremental update; `_pixmap_cache` lifecycle
- `app/views/sections/preview_panel.py` — `_on_item_loaded` no longer forces full gallery clear on same-item updates
- `app/viewmodels/preview_panel_vm.py` — add INI parse cache by item_id; `_load_item` cache hit path
- `app/services/file_watcher_service.py` — `recursive=True`; suppression logic refinement
- `app/viewmodels/main_window_vm.py` — external vs internal event differentiation; debounce refinement
- `app/viewmodels/mod_list_vm.py` — toggle path avoids `load_items` full reload
