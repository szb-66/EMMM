## Context

Both `FoldergridPanel` and `ObjectlistPanel` handle `items_updated` by destroying all child widgets and recreating them — even when the new item list is a reordered subset of the old one. This causes visible flicker (blank panel between destruction and recreation). Separately, the objectlist watch key is missing `**/preview*.*` from its ignore patterns, so internal preview-image metadata syncs trigger `request_main_refresh()`.

## Goals / Non-Goals

**Goals:**
- Zero visible flicker when `items_updated` fires, regardless of what triggered it
- Widget reuse by item ID: same ID → same widget object, just repositioned and updated
- Consistent ignore patterns between objectlist and foldergrid watcher keys

**Non-Goals:**
- Changing the FlowLayout / QListWidget container types
- Adding animation or transition effects
- Changing how `item_needs_update` works (it already does single-widget updates correctly)

## Decisions

### Decision 1: Diff-based widget reuse in `_on_items_updated`

**Approach:** Compute three sets from item IDs — `added`, `removed`, `kept` — and act on each:

```
new_ids = {item["id"] for item in items_data}
old_ids = set(self._item_widgets.keys())

removed = old_ids - new_ids  → destroy these widgets
kept    = old_ids & new_ids  → reuse these widgets (update data in place)
added   = new_ids - old_ids  → create new widgets for these
```

Then iterate `items_data` in order, taking each widget from either the kept pool or creating a new one, and placing it in the container in the new order.

**FoldergridPanel (FlowLayout):**
1. Collect widgets to remove: for id in `removed`, `layout.removeWidget(w)` + `w.deleteLater()`
2. Build new ordered widget list: for each item in `items_data`, if `id in kept` reuse existing widget (call `set_data()`), else create new `FolderGridItemWidget`
3. Remove all widgets from layout, re-add in new order, update `_item_widgets` dict

**ObjectlistPanel (QListWidget):**
1. For ids in `removed`: find row of `QListWidgetItem`, `list_widget.takeItem(row)`, remove from `_item_widgets`
2. For each item in `items_data` in order:
   - If `id in kept`: find existing `QListWidgetItem`, update its `ObjectListItemWidget` via `set_data()`, move item to correct row
   - If `id in added`: create new `QListWidgetItem` + `ObjectListItemWidget`, insert at position
3. Update `_item_widgets` dict

**Why this works for reordering:** Sorting/filtering changes the order of `items_data` but the item IDs stay the same. By reusing widgets by ID and repositioning them, we get a smooth reorder without destruction flicker.

**Alternative considered:** Diff-free approach — just reposition existing widgets and only create/remove at the edges. Rejected: too fragile when items can be added/removed.

### Decision 2: Add `**/preview*.*` to objectlist ignore patterns

**Approach:** One-line addition in `MainWindowViewModel.__init__`:

```python
self._file_watcher.ignore_patterns(
    "objectlist",
    ["**/info.json", "**/properties.json", "**/_thumb.*", "**/preview*.*"],
)
```

**Why:** `hydrate_item` syncs preview image metadata to `info.json`. The `info.json` write is already filtered by both keys. But the actual preview image files (`preview-1.webp`, `preview.webp`) can also be read/modified during hydration, triggering spurious watchdog events on the objectlist key (which covers the parent mods directory recursively). Adding `**/preview*.*` prevents these from cascading into a full `request_main_refresh()`.

## Risks / Trade-offs

- **Risk: Widget reuse with stale data** → Mitigation: `set_data()` updates all widget fields from the new item_data dict. If `set_data` is incomplete for some fields, stale data could show. Each widget's `set_data` already handles the full update path.
- **Risk: QListWidget row management complexity** → Mitigation: Keep the logic simple — remove stale, update kept in-place, insert new at correct position. Test with add/remove/reorder scenarios.
