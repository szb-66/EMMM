## 1. Remove Queue and Replay from FileWatcherService

- [x] 1.1 Remove `_suppressed_event_queue` dict from `__init__`
- [x] 1.2 Remove `queue_event()` method entirely
- [x] 1.3 Remove `replay_queued_events()` method entirely
- [x] 1.4 Simplify `_DirectoryEventHandler.on_any_event`: keep `is_suppressed` check + `return`, remove `queue_event` call
- [x] 1.5 Remove `self.replay_queued_events(key)` call from `suppress_watch`'s `clear_suppression` callback
- [x] 1.6 Remove `self._suppressed_event_queue.pop(key, None)` from `clear_watch`

## 2. Verification

- [x] 2.1 Run test suite: `python -m unittest discover tests -v` — all tests pass
- [ ] 2.2 Manually verify: toggle a mod → no flicker 5 seconds later
