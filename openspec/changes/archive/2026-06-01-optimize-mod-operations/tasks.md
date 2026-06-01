## 1. Thumbnail Gallery — Incremental Update

- [x] 1.1 Refactor `set_image_paths` to compute three-way diff (add/remove/keep) between current and new image lists
- [x] 1.2 Remove `_clear_gallery()` call from `set_image_paths`; only delete widgets for removed paths
- [x] 1.3 Only create `ThumbnailGalleryLabel` widgets for newly added paths
- [x] 1.4 Update index references on kept widgets without destroying them
- [x] 1.5 Re-test `_update_thumb_sizes` with incremental widget set

## 2. Pixmap Cache — Persist Across Item Transitions

- [x] 2.1 Replace `_pixmap_cache.clear()` with selective key removal in `_clear_gallery`
- [x] 2.2 Add `clear_cache()` signal that explicitly clears the cache when images are deleted
- [x] 2.3 Wire cache invalidation from `_on_thumbnail_operation_complete` to gallery's cache clear signal
- [x] 2.4 Replace `dict` with `OrderedDict` capped at 200 entries (LRU eviction)
- [ ] 2.5 Verify re-selecting a mod reads from cache (not disk) via `QPixmap` load tracing

## 3. INI Parse Cache — Per-Item Caching

- [x] 3.1 Add `_ini_cache: dict[str, tuple[list[KeyBinding], float]]` to `PreviewPanelViewModel`
- [x] 3.2 In `_load_item`, check cache before spawning worker — keyed by `item_id`
- [x] 3.3 Add mtime check: compare mod folder's `.ini` files' max mtime against cached timestamp
- [x] 3.4 On cache hit, assign `self.editable_keybindings` directly and call `ini_config_ready.emit` synchronously
- [x] 3.5 Invalidate cache entry when `save_ini_config` succeeds
- [x] 3.6 Invalidate cache entry when `update_view_for_item` receives an item with changed `folder_path`

## 4. File Watcher — Recursive Mode

- [x] 4.1 Change `recursive=False` to `recursive=True` in `FileWatcherService.watch_directory()`
- [x] 4.2 Add directory event filtering in `_DirectoryEventHandler` to avoid redundant directory-creation events
- [ ] 4.3 Verify that deleting a subfolder within a watched mod directory triggers `directory_changed`

## 5. File Watcher — External Event Preservation

- [x] 5.1 Add `_suppressed_event_queue: dict[str, set[str]]` to `FileWatcherService` (keyed by watcher key, values are src_paths)
- [x] 5.2 In `_DirectoryEventHandler.on_any_event`, when suppressed: add `src_path` to queue instead of dropping
- [x] 5.3 In `clear_suppression` callback (or suppression timer callback), replay queued events
- [x] 5.4 Deduplicate queued events per `src_path` before replay
- [ ] 5.5 Verify: right-click toggle then immediately delete a different mod folder in Explorer — deletion syncs correctly

## 6. Toggle — Avoid Full Reload

Note: Objectlist toggle (character enable/disable) must reload foldergrid because all mod paths become stale when the parent folder is renamed. Foldergrid item toggle is already efficient via `_on_foldergrid_item_modified` → `update_view_for_item`.

- [x] 6.1 In `main_window_vm._on_watched_directory_changed`, restart debounce timer instead of dropping events during suppression
- [x] 6.2 Foldergrid view already handles `item_needs_update` via `FolderGridItemWidget.set_data()` — confirmed working
- [x] 6.3 Verify: toggling a mod's enabled state updates UI in <100ms without directory re-scan

## 7. Preview Panel — Targeted Update Without Full Rebuild

- [x] 7.1 In `preview_panel._on_item_loaded`, skip `self.clear_panel()` and `self._clear_ini_layout()` when the item data is for the same `current_item_model` (toggle case — only status changed)
- [x] 7.2 Add lightweight update path that only refreshes the status switch and title without touching gallery or INI section
- [ ] 7.3 Verify: toggling a mod updates only the enabled/disabled indicator, not the entire panel
