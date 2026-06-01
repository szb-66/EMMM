## 1. FoldergridPanel — Diff-based widget reuse

- [x] 1.1 Refactor `_on_items_updated` in `foldergrid_panel.py`: compute `added`/`removed`/`kept` ID sets from new items_data vs `_item_widgets`
- [ ] 1.2 Destroy widgets in `removed` set: remove from layout, `deleteLater()`
- [ ] 1.3 Create widgets for `added` set: new `FolderGridItemWidget`, connect signals
- [ ] 1.4 Reorder: collect all widgets in `items_data` order (reusing `kept` set), re-add to layout
- [ ] 1.5 Update `_item_widgets` dict to match new widget set

## 2. ObjectlistPanel — Diff-based widget reuse

- [x] 2.1 Refactor `_on_items_updated` in `objectlist_panel.py`: compute `added`/`removed`/`kept` ID sets
- [ ] 2.2 Remove `QListWidgetItem` entries for `removed` ids via `takeItem(row)`
- [ ] 2.3 Update `ObjectListItemWidget` for `kept` ids via `set_data()`, reposition rows
- [ ] 2.4 Create new `QListWidgetItem` + `ObjectListItemWidget` for `added` ids at correct positions
- [ ] 2.5 Update `_item_widgets` dict to match new widget set

## 3. Ignore Pattern Fix

- [x] 3.1 Add `**/preview*.*` to objectlist's `ignore_patterns` in `main_window_vm.py`

## 4. Verification

- [x] 4.1 Run test suite: `python -m unittest discover tests -v` — all tests pass
- [ ] 4.2 Manually verify: toggle a mod → sort reorders without flicker
- [ ] 4.3 Manually verify: click a mod in foldergrid → no panel flash
- [ ] 4.4 Manually verify: search/filter → list updates without blank frame
