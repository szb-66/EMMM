## 1. Core Fix

- [x] 1.1 Add `self.apply_filters_and_search()` call in `_on_toggle_status_finished` after updating `master_list` and `displayed_items`, before emitting `item_needs_update` — matching the pattern used in `_on_pin_status_finished`
- [x] 1.2 Remove duplicate `item_processing_finished.emit` calls in `_on_toggle_status_finished` if any were left from the old broken path

## 2. Verification

- [ ] 2.1 Manually verify: toggle a mod's status → list re-sorts immediately (not after 4–5 seconds)
- [ ] 2.2 Manually verify: toggle does NOT trigger a directory scan (no `load_items` call in logs for the toggled context)
- [ ] 2.3 Manually verify: left panel (objectlist) does NOT refresh when toggling a foldergrid mod
- [x] 2.4 Run existing test suite: `python -m unittest discover tests -v` — all 16 tests pass
