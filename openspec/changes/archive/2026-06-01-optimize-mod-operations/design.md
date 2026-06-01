## Context

The app uses an MVVM architecture with PyQt6. The thumbnail gallery (ThumbnailSliderWidget) fully rebuilds all widget children and clears the in-memory pixmap cache on every item transition and every thumbnail mutation. The INI keybinding parser re-reads and re-parses `.ini` files each time a mod is selected, even if the mod's content has not changed. The file watcher (watchdog) operates in non-recursive mode with a 5-second suppression window after every internal operation, silently dropping external filesystem events during that window.

User-facing symptoms: right-click toggle lag, image add/remove lag, external folder deletion not reflected in UI.

## Goals / Non-Goals

**Goals:**
- Thumbnail gallery add/remove operations affect only the target thumbnail — no full rebuild
- Pixmap cache persists across item transitions; re-selecting a mod with previously loaded images does not re-read from disk
- INI keybinding parse results cached per mod `item_id` with automatic invalidation when `.ini` files change on disk
- File watcher monitors subdirectory changes (recursive mode)
- External filesystem events are preserved even when a suppression window is active; only events matching the known internal operation are suppressed
- Toggling a mod status updates the model in-place and pushes a targeted widget update — no directory re-scan

**Non-Goals:**
- Full skeleton cache layer across directory switches (out of scope — the skeleton scan over a typical <500-item directory is <50ms)
- Periodic heartbeat resync (the recursive watcher + event preservation makes this unnecessary)
- Virtual scrolling for the thumbnail gallery (viewport size is ~10 thumbnails; full rebuild was the real cost)
- Image compression/encoding changes

## Decisions

### Decision 1: Incremental gallery update via diff-based set_image_paths

**Approach:** `set_image_paths` computes a three-way diff (add, remove, keep) between the current `_image_paths` and the new list. Only removed indices have their widgets deleted; only new paths have widgets created; kept items update their index but reuse the existing widget and cached pixmap.

**Alternatives considered:**
- Full clear-and-rebuild (current, rejected): simple but O(n) widget destruction + O(n) QPixmap I/O per call.
- Virtual list (rejected): over-engineered for ~50 items; proper for 500+.
- Swap `QHBoxLayout` contents out entirely (rejected): same cost as current approach.

**Why diff-based:** Widget creation/destruction is the dominant cost. For an add-image operation, the diff is typically `add=[1], remove=[], keep=[0..N]` — only 1 new widget created, 0 destroyed, N pixmaps reused from cache.

### Decision 2: Persistent pixmap cache across item transitions

**Approach:** The `_pixmap_cache` dict survives `set_image_paths` calls. It is cleared only when the widget receives an explicit `clear_cache()` signal (e.g., when images are deleted from disk). Cache key is `str(image_path)`; LRU eviction is not needed at current scale (<200 entries total).

**Why:** The cache clear was the #1 reason for add-image lag — every existing thumbnail re-read from disk even though none had changed.

### Decision 3: INI parse cache in PreviewPanelViewModel

**Approach:**  
```python
self._ini_cache: dict[str, tuple[list[KeyBinding], list[Path]]] = {}
```
Keyed by `item_id`. On `_load_item`, if `item_id` is in cache AND the mod folder's `.ini` files have not been modified (stored `mtime` check), the cached result is used directly on the UI thread instead of spawning a worker. Cache is invalidated when the user saves INI changes.

**Alternatives considered:**
- File-system watcher for per-file invalidation (rejected): complex; mtime check is cheap and sufficient.
- No cache (current, rejected): re-parses every selection switch; dominant cost for mods with many `.ini` files.

### Decision 4: File watcher recursive mode

**Approach:** Change `recursive=False` to `recursive=True` in `FileWatcherService.watch_directory()`. Watchdog's `PatternMatchingEventHandler` already filters events; we add `DirectoryEventHandler` to ignore directory creation events at the root level (only care about file changes and deletions).

**Why:** The non-recursive watch was the root cause of "deleted nested folder not synced." There is no measurable performance cost for recursive watching at the scale of individual mod folders (typically <200 files).

### Decision 5: External event preservation during suppression

**Approach:** Instead of dropping all events during suppression, the `_DirectoryEventHandler` queues suppressed events and replays them after the suppression token clears. The queue is keyed by `src_path` — duplicate events for the same path within the suppression window are collapsed (watchdog fires `modified` multiple times during a rename).

**Why:** The original blanket 5-second suppression was designed to prevent flicker from internal rename operations (which fire multiple watchdog events). But it also dropped legitimate external changes made during that window. The queue-and-replay approach preserves external events while still collapsing internal noise.

### Decision 6: Toggle avoids full reload domino

**Approach:** `_on_toggle_status_finished` already updates the item in `master_list` and `displayed_items` in-place. The domino effect (`foldergrid_item_modified` → `_on_foldergrid_item_modified` → `preview_panel_vm.update_view_for_item`) already works without a full reload. The remaining issue is `main_window_vm._on_active_object_modified` calling `foldergrid_vm.load_items(...)`. This call will be replaced with a targeted signal to the foldergrid view to update just the one item's visual representation (status indicator, text styling).

**Why:** The `load_items` call triggers a full `os.scandir` + skeleton rebuild + filter re-application + selection restoration, which is wasteful when only one item's `DISABLED ` prefix changed.

## Risks / Trade-offs

- **Risk: Recursive watcher floods events on large mod folders** → Mitigation: The 400ms debounce timer already coalesces rapid-fire events. For typical mod folders (<200 files), the total event volume is low.
- **Risk: INI cache serves stale data** → Mitigation: mtime check on the mod folder's `.ini` files before cache hit. If any `.ini` file has a newer mtime than the cached parse, re-parse.
- **Risk: Pixmap cache grows unbounded** → Mitigation: Fixed-size `OrderedDict` (200 entries) with LRU eviction. `clear_cache()` signal clears the dict when images are physically deleted.
- **Risk: Queued suppression events trigger unexpected refreshes** → Mitigation: The queue replay includes its own debounce. If the original operation already updated the UI via the targeted widget path, the replayed event causes no visible change (it re-scans a directory that is already consistent).
