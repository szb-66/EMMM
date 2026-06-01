## Why

Toggling a mod's enabled/disabled status in the foldergrid does not immediately re-sort the list. The user sees the toggle animation complete but the item stays in its original position for 4–5 seconds — until the watchdog suppression window expires and a filesystem event triggers a full `load_items()` cycle that finally calls `apply_filters_and_search()`. The sort should happen instantly, in memory, without any directory scan.

## What Changes

- **`_on_toggle_status_finished` calls `apply_filters_and_search()`**: After updating the item in `master_list` and `displayed_items`, immediately re-apply filters and sorting so the "enabled mods first" rule takes effect in the same frame.
- **Reduce cross-panel watchdog suppression scope**: The sort is now applied in the toggle callback itself — the watchdog replay becomes a no-op from the user's perspective. The 5-second suppression window that was masking the missing sort call can be shortened or scoped more narrowly.

## Capabilities

### New Capabilities

None. This is a behavioral fix, not a new capability.

### Modified Capabilities

- `viewmodels`: `_on_toggle_status_finished` in `ModListViewModel` MUST call `apply_filters_and_search()` after updating the item model, matching the existing behavior of `_on_pin_status_finished`. This ensures the enabled/disabled sort order is applied synchronously without depending on a filesystem event.

## Impact

- `app/viewmodels/mod_list_vm.py` — `_on_toggle_status_finished`: add `apply_filters_and_search()` call
- `app/viewmodels/main_window_vm.py` — `_suppress_watched_refresh`: may reduce cross-suppression or duration since sort is no longer dependent on watchdog replay
