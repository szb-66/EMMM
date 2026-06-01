## MODIFIED Requirements

### Requirement: Item operations

All item operations follow the same pattern: guard (`_processing_ids` check) → Worker → result slot → state update → re-sort → signal.

Operations that change an item's sort key (status toggle, pin toggle) MUST call `apply_filters_and_search()` in their result slot to immediately re-sort the displayed list. The sort order SHALL reflect the new state without waiting for a filesystem event.

`ModListViewModel` exposes these item operations:
- `toggle_item_status`, `toggle_pin_status`, `rename_item`, `delete_item`
- `convert_object_type`, `update_object_item`, `initiate_sync_for_item`

#### Scenario: Toggle status applies sort immediately

- **WHEN** a foldergrid item's status is toggled via `toggle_item_status` and the background worker returns success
- **THEN** `_on_toggle_status_finished` SHALL call `apply_filters_and_search()` after updating the item in `master_list` and `displayed_items`
- **AND** the displayed list SHALL re-sort with the "enabled first, then disabled, then alphabetical" rule applied
- **AND** the sort SHALL complete without triggering a directory scan (`load_items`)

#### Scenario: Toggle pin applies sort immediately

- **WHEN** an item's pin status is toggled via `toggle_pin_status` and the background worker returns success
- **THEN** `_on_pin_status_finished` SHALL call `apply_filters_and_search()` after updating the item in the lists
- **AND** the displayed list SHALL re-sort with pinned items first

#### Scenario: Rename does not require re-sort

- **WHEN** an item is renamed via `rename_item` and the background worker returns success
- **THEN** `_on_rename_finished` SHALL NOT call `apply_filters_and_search()` because renaming does not change the sort key (name is the last sort tiebreaker and is already reflected in `update_item_in_list`)
