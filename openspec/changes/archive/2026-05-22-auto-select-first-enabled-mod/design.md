## Context

When a user selects an object in the object list, `MainWindowViewModel.set_active_object()` triggers `foldergrid_vm.load_items()`, which asynchronously loads mod skeletons and calls `_on_skeletons_loaded()` on completion. Currently, `_on_skeletons_loaded()` only restores a previous selection or selects a newly created item — if neither applies, no mod is selected. The foldergrid panel (`FolderGridPanel._on_items_updated`) receives the `item_id_to_select` parameter from the `items_updated` signal but currently ignores it, using only the list of item data dicts to rebuild the grid.

The `objectlist_panel.py` already implements the correct pattern: its `_on_items_updated` accepts `item_id_to_select` and programmatically emits `item_selected` when it's set.

## Goals / Non-Goals

**Goals:**
- When an object is selected and its foldergrid loads, auto-select the first enabled mod
- If no mod is enabled, auto-select the first mod in the list
- The auto-selected mod should appear in the preview panel (not just visual highlight)
- Maintain all existing selection restoration logic (newly created items, previously selected items take priority)

**Non-Goals:**
- No changes to the objectlist selection behavior
- No changes to the toggle/enable/disable flows
- No changes to bulk operations or filtering

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where to add default selection logic | `_on_skeletons_loaded()` in `ModListViewModel` | Selection state is already managed here; avoids adding new signals or coupling. The logic runs after the existing restoration checks, so priority is preserved: newly created > previously selected > default selection. |
| How to trigger preview panel update | Accept `item_id_to_select` in `FolderGridPanel._on_items_updated()` | Consistent with the existing pattern in `ObjectListPanel._on_items_updated()`. Avoids introducing a new signal just for auto-selection. |
| How to find the default item | `next()` with `ModStatus.ENABLED` filter, fallback to `master_list[0]` | Simplest expression of the requirement. Both lookups are O(n) but on in-memory lists, negligible. |

## Risks / Trade-offs

- **Filter conflict**: If a search/filter is active when an object is selected, the auto-selected mod might not appear in `displayed_items`. The `items_updated` signal would be emitted with the id but the view won't find the widget → falls through to no selection. This is acceptable because filtering during object-switching is an unusual edge case and the behavior is no worse than today.
- **Toggle → foldergrid refresh**: When toggling a mod's status (enabled/disabled), `_on_active_object_modified` reloads the foldergrid. The existing restoration logic handles this correctly — `last_selected_item_id` is already set, so it restores the same mod's selection. The new default logic only fires when no prior selection exists.
