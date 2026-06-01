## Why

After a mod status toggle, `FileWatcherService` queues the watchdog event for 5 seconds and replays it when suppression expires. The replay triggers `load_items()` — a full directory scan and widget rebuild — causing the entire list to flash empty then repopulate. This was originally necessary to re-sort the list after a status change, but `instant-toggle-sort` already made sorting synchronous (in `_on_toggle_status_finished`). The replay now serves no purpose except to produce a visible flicker.

## What Changes

- **Remove suppressed event queue and replay from `FileWatcherService`**: Delete `_suppressed_event_queue`, `queue_event()`, and `replay_queued_events()`. During suppression, events are silently dropped — the same behavior used before the queue was added.
- **`suppress_watch` no longer replays on expiry**: The `clear_suppression` callback in `suppress_watch` is simplified to only clear the token.

## Capabilities

### New Capabilities

None. This is a removal of redundant behavior.

### Modified Capabilities

- `services`: Remove the "External event preservation during suppression" mechanism (`queue_event` / `replay_queued_events`). The suppression window now drops all events, as it did before the preservation logic was added. This is safe because (a) `ignore_patterns` already filters internal JSON/metadata writes that would otherwise flood events, and (b) `apply_filters_and_search()` in `_on_toggle_status_finished` handles sorting synchronously — the two original reasons for preserving events no longer exist.

## Impact

- `app/services/file_watcher_service.py` — remove `_suppressed_event_queue` dict, `queue_event()`, `replay_queued_events()`, and the `clear_suppression` callback's replay call. Simplify `_DirectoryEventHandler.on_any_event` to silently return when suppressed (no queuing).
- `openspec/specs/services.md` — delta: remove the "External event preservation" requirement.
