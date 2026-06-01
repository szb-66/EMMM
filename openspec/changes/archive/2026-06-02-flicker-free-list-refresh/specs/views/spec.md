## ADDED Requirements

### Requirement: List panels reuse existing widgets on update

When `items_updated` fires with a new item list, `FoldergridPanel` and `ObjectlistPanel` SHALL reuse existing child widgets for items whose IDs appear in both the old and new lists. Widgets SHALL be destroyed only for removed items, and created only for added items. The panel SHALL NOT appear blank between updates.

#### Scenario: Sort reorder reuses all widgets

- **WHEN** `items_updated` emits a list containing the same item IDs in a different order
- **THEN** no widgets SHALL be destroyed or created
- **AND** existing widgets SHALL be repositioned to match the new order
- **AND** the panel SHALL NOT flash empty during the update

#### Scenario: Item added creates only the new widget

- **WHEN** `items_updated` emits a list with one additional item ID compared to the current widget set
- **THEN** exactly one new widget SHALL be created for the added item
- **AND** all existing widgets SHALL be reused without destruction

#### Scenario: Item removed destroys only the stale widget

- **WHEN** `items_updated` emits a list with one fewer item ID compared to the current widget set
- **THEN** exactly one widget SHALL be destroyed for the removed item
- **AND** all other widgets SHALL be reused
