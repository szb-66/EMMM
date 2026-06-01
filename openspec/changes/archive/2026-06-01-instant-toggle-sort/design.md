## Context

`_on_toggle_status_finished` in `ModListViewModel` handles the result of toggling a mod's enabled/disabled status. It updates the item in `master_list` and `displayed_items` and emits `item_needs_update` for the view — but it does NOT call `apply_filters_and_search()`. The sort order ("enabled → disabled → alphabetical") is defined inside `apply_filters_and_search`, so the toggle result is invisible to the user until some other trigger re-sorts the list.

Today, that trigger is the watchdog replay: 5 seconds after the toggle, the suppression window expires, `FileWatcherService.replay_queued_events` fires `directory_changed` for both `foldergrid` and `objectlist` keys, and `_refresh_watched_context("foldergrid")` calls `load_items()` which internally calls `apply_filters_and_search()`.

`_on_pin_status_finished` — the sibling callback for pin toggles — already calls `apply_filters_and_search()` and provides instant sort feedback. The two callbacks should be consistent.

## Goals / Non-Goals

**Goals:**
- Toggle status → list re-sorts in the same frame (no visible delay)
- `_on_toggle_status_finished` and `_on_pin_status_finished` use the same pattern
- No directory scan, no `load_items()`, no filesystem interaction for the sort

**Non-Goals:**
- Changing the sort algorithm itself
- Removing the watchdog suppression mechanism (it still prevents redundant `load_items` calls from filesystem events)
- Changing the "enabled first" sort rule
- Impacting objectlist toggle behavior (which legitimately needs to reload foldergrid because all child paths become stale when the parent folder is renamed)

## Decisions

### Decision 1: Add `apply_filters_and_search()` to `_on_toggle_status_finished`

**Approach:** After `self.master_list[master_idx] = new_item` and `self.displayed_items[display_idx] = new_item`, call `self.apply_filters_and_search()`. This is exactly what `_on_pin_status_finished` does at line 371.

```python
# Before (current):
self.master_list[master_idx] = new_item
self.displayed_items[display_idx] = new_item
self.item_needs_update.emit(self._create_dict_from_item(new_item))
self.item_processing_finished.emit(item_id, True)
# ... domino signals

# After:
self.master_list[master_idx] = new_item
self.displayed_items[display_idx] = new_item
self.apply_filters_and_search()                             # ← added
self.item_needs_update.emit(self._create_dict_from_item(new_item))
self.item_processing_finished.emit(item_id, True)
# ... domino signals
```

`apply_filters_and_search()` is a pure in-memory operation:
1. Iterates `self.master_list` (no disk I/O)
2. Applies active filters and search query
3. Sorts with `sorted(key=lambda x: (score, not pinned, status != ENABLED, name))`
4. Assigns `self.displayed_items`
5. Emits `items_updated` signal to the view

**Alternatives considered:**
- **Do nothing (current):** Sort depends on watchdog replay. 4–5 second user-visible delay. Rejected.
- **Call `load_items()` instead:** Triggers `os.scandir` + skeleton rebuild. Unnecessary — the data is already correct in `master_list`. Rejected.
- **Manually re-sort `displayed_items` without `apply_filters_and_search()`:** Duplicates sorting logic. Violates DRY. Rejected.

### Decision 2: Keep existing suppression mechanism unchanged

**Rationale:** The suppression prevents watchdog from triggering redundant `load_items()` calls after internal operations. Even though the sort is now immediate, suppression still prevents an unnecessary directory scan ~400ms after each toggle. Removing it would cause flicker from `load_items` rebuilding the list that was already sorted.

The 5-second duration and cross-panel scope remain as-is for this change. They can be tuned in a follow-up if needed.

## Risks / Trade-offs

- **Risk: `apply_filters_and_search()` emits `items_updated` which rebuilds all list widgets** → Mitigation: This is the same behavior as pin toggle and search/filter changes. The view already handles `items_updated` efficiently for typical mod counts (<500 items). If widget rebuild becomes a bottleneck, it can be addressed with view-level widget reuse — out of scope for this change.

- **Risk: `item_needs_update` followed by `apply_filters_and_search` causes double render** → Mitigation: `apply_filters_and_search` is called first, then `item_needs_update`. The view's `items_updated` handler will position and render all visible items; the subsequent `item_needs_update` for the toggled item is redundant but harmless (it re-emits data for a widget that already has the correct data from `items_updated`). Acceptable for now; can be optimized later.
