## Why

Every `items_updated` emission destroys all list widgets and rebuilds them from scratch. Between `clear_items()` and widget recreation, the user sees an empty panel — visible flicker. This happens on sort, filter, hydration, and watchdog-triggered refreshes. Additionally, the objectlist watcher key is missing `**/preview*.*` in its ignore patterns, so internal preview-image writes cascade into `request_main_refresh()` that reloads both panels.

## What Changes

- **Smart diff-based `_on_items_updated`**: Compare new item IDs against existing widget IDs. Reuse widgets for unchanged items, create only for new items, remove only stale ones. Eliminates visible flicker regardless of trigger.
- **Consistent ignore patterns**: Add `**/preview*.*` to the objectlist key so both watcher keys filter the same internal noise.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `views`: `_on_items_updated` in `FoldergridPanel` and `ObjectlistPanel` MUST reuse existing widgets by item ID instead of destroying all and rebuilding. The visual result of any sort or filter change MUST be a smooth reorder with no blank-then-repopulate flash.

## Impact

- `app/views/sections/foldergrid_panel.py` — `_on_items_updated`: diff-based widget reuse
- `app/views/sections/objectlist_panel.py` — `_on_items_updated`: diff-based widget reuse
- `app/viewmodels/main_window_vm.py` — `__init__`: add `**/preview*.*` to objectlist ignore patterns
