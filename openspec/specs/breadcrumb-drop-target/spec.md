# Breadcrumb Drop Target

**Responsibility:** Define drag-and-drop behavior for `BreadcrumbWidget` as an ancestor-directory drop target for internal mod drags.

## Purpose

Enable users to move mods into ancestor directories by dropping them onto breadcrumb navigation segments. When a mod card is dragged over a breadcrumb segment representing a directory higher in the hierarchy than the current directory, the segment lights up and accepts the drop, routing the move through the existing `ModListViewModel.move_item_to_folder` method. The current (last) segment rejects drops since the mod is already in that directory.

## Requirements

### Requirement: Breadcrumb widget accepts ancestor-directory drops

`BreadcrumbWidget` SHALL accept internal mod drags carrying `EMMM_MOD_MIME_TYPE`
and move the dropped mod into the directory of the breadcrumb segment under the
cursor, provided that segment is a strict ancestor of the current directory.
The current (last) segment SHALL reject the drop because the mod is already in
that directory. Drop handling SHALL be routed via a new
`drop_requested(item_id: str, target_path: Path)` signal that the panel wires
to `ModListViewModel.move_item_to_folder`; no new service or viewmodel method
SHALL be introduced.

#### Scenario: Drag over an ancestor segment highlights it and accepts

- **WHEN** the user drags a mod card with the internal MIME type and the cursor
  is over a visible breadcrumb segment whose index is strictly less than the
  index of the current (last) segment
- **THEN** `BreadcrumbWidget.dragMoveEvent` SHALL call
  `acceptProposedAction()`
- **AND** that segment SHALL be highlighted (its `isHover` set to `True` and
  `update()` called)
- **AND** any previously highlighted segment SHALL have its `isHover` reset to
  `False` and be repainted

#### Scenario: Drag over the current segment is rejected

- **WHEN** the user drags a mod card with the internal MIME type and the cursor
  is over the current (last) breadcrumb segment
- **THEN** `BreadcrumbWidget.dragMoveEvent` SHALL call `event.ignore()`
- **AND** that segment SHALL NOT be highlighted
- **AND** Qt SHALL render the forbidden cursor for as long as the cursor stays
  over the current segment

#### Scenario: Drag over a gap between segments is rejected

- **WHEN** the user drags a mod card with the internal MIME type and the cursor
  is not over any visible breadcrumb segment
- **THEN** `BreadcrumbWidget.dragMoveEvent` SHALL call `event.ignore()`
- **AND** no segment SHALL be highlighted

#### Scenario: Dropping on an ancestor segment moves the mod

- **WHEN** the user releases the drag over an ancestor breadcrumb segment that
  was accepted by `dragMoveEvent`
- **THEN** `BreadcrumbWidget.dropEvent` SHALL decode the dropped mod's
  `item_id` from the MIME data
- **AND** SHALL emit `drop_requested(item_id, segment_path)` where
  `segment_path` is the cumulative `Path` of the segment under the cursor taken
  from `_segment_paths`
- **AND** SHALL call `event.acceptProposedAction()`
- **AND** the panel SHALL route the signal to
  `ModListViewModel.move_item_to_folder(item_id, segment_path)`

#### Scenario: Drop target path is resolved at drop time

- **WHEN** `_segment_paths` was rebuilt between the `dragMoveEvent` that set the
  hover index and the `dropEvent` (e.g. a concurrent `path_changed`)
- **AND** the hover index is no longer in range of the rebuilt
  `_segment_paths`
- **THEN** `dropEvent` SHALL NOT emit `drop_requested`
- **AND** SHALL call `event.ignore()`

#### Scenario: Drag leaves the breadcrumb clears highlight

- **WHEN** the user drags a mod card out of the breadcrumb widget without
  dropping
- **THEN** `BreadcrumbWidget.dragLeaveEvent` SHALL reset `isHover` to `False`
  on every highlighted segment and repaint it
- **AND** SHALL clear the internal hover index

#### Scenario: Hidden breadcrumb segments are not drop targets

- **WHEN** the breadcrumb trail is longer than the breadcrumb width and some
  segments are elided into the `elideButton` menu
- **THEN** `dragMoveEvent` SHALL skip every `BreadcrumbItem` whose
  `isVisible()` returns `False` when hit-testing
- **AND** SHALL skip the `elideButton` itself

#### Scenario: Breadcrumb widget advertises itself as a drop target

- **WHEN** a `BreadcrumbWidget` is constructed
- **THEN** it SHALL call `setAcceptDrops(True)`
- **AND** its `dragEnterEvent` SHALL call `acceptProposedAction()` for MIME
  data carrying `EMMM_MOD_MIME_TYPE` and otherwise defer to the superclass
