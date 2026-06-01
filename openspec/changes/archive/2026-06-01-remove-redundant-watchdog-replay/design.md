## Context

`optimize-mod-operations` Decision 5 introduced `_suppressed_event_queue` and `replay_queued_events()` so external filesystem changes during the 5-second suppression window wouldn't be silently dropped. At the time, the sort-after-toggle depended on the replay: `_on_toggle_status_finished` did not call `apply_filters_and_search()`, so the only way the list got re-sorted was when `replay_queued_events` → `load_items()` → `apply_filters_and_search()`.

Two things changed since:

1. `ignore_patterns` (from our TDD slices) now filters internal JSON/metadata writes — these no longer trigger watchdog events at all.
2. `instant-toggle-sort` added `apply_filters_and_search()` to `_on_toggle_status_finished` — the sort is synchronous, in-memory, no filesystem dependency.

The replay now causes a visible flash: `load_items()` emits `items_updated([], None)` which destroys all view widgets, then rebuilds them from a re-scan of the same directory that hasn't changed.

## Goals / Non-Goals

**Goals:**
- Eliminate the visible flicker 5 seconds after every toggle/rename/delete
- Simplify `FileWatcherService` by removing dead code
- Preserve the token-based suppression mechanism (it still prevents redundant `load_items` calls during the initial rename event)

**Non-Goals:**
- Changing the 5-second suppression duration
- Removing the cross-panel suppression in `MainWindowViewModel`
- Preserving external events during suppression (acceptable trade-off for no flicker)

## Decisions

### Decision 1: Drop events during suppression — no queue, no replay

**Approach:** Revert to the pre-queue behavior: when `is_suppressed(key)` is true, `_DirectoryEventHandler.on_any_event` returns immediately without recording the event. Remove `_suppressed_event_queue`, `queue_event()`, `replay_queued_events()`.

Code removed from `FileWatcherService`:
```
__init__:   self._suppressed_event_queue: dict[str, set[str]] = {}
on_any_event:  self._owner.queue_event(...) call (keep the return)
queue_event(): entire method
replay_queued_events(): entire method
suppress_watch.clear_suppression: self.replay_queued_events(key) call
clear_watch: self._suppressed_event_queue.pop(key, None)
```

**Why:** The replay exists to re-sort the list after toggle. With `apply_filters_and_search()` in the toggle callback, the sort is instant. The replay now only causes a visible empty-then-repopulate cycle with no data change.

**Alternative considered:** Preserve the queue but debounce the replay differently (e.g., skip `load_items` if `master_list` already matches disk). Rejected — adds complexity for a scenario (external Explorer change during 5s suppression window) that is extremely rare and trivially fixable by clicking Refresh.

### Decision 2: Keep `suppress_watch` token mechanism intact

**Rationale:** The token-based suppression is still needed. Without it, the initial rename event (at ~50ms, not the replay at 5s) would trigger `_refresh_watched_context` → `load_items()` ~400ms after toggle, causing a flicker ~450ms post-toggle. The VM already patched the item at ~80ms, so that `load_items` would be just as redundant as the replay — it just happens sooner and the sort hasn't drifted.

The suppression blocks that first event. The replay was the tail end of the same mechanism — the re-emission of the blocked event 5 seconds later. Removing the replay means the first event is blocked, and there IS no second emission.

## Risks / Trade-offs

- **Risk: External Explorer change during 5s suppression window is lost** → A user toggles a mod, then within 5 seconds switches to Explorer and deletes/creates another mod folder. That change won't appear in the UI until the next manual refresh or navigation change. This is acceptable: the window is short, the scenario is rare, and the fix is one click.
