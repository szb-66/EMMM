## Why

Currently, when a user clicks an object in the object list, the foldergrid loads all its mods but does not select any by default. The user has to manually click a mod to see its details in the preview panel. This creates unnecessary friction — the most natural default is to auto-select the first enabled mod (or the first mod if none are enabled), so the preview panel immediately shows useful content.

## What Changes

- **ModListViewModel._on_skeletons_loaded()**: When loading mods into the foldergrid and no prior selection exists to restore, automatically select the first mod whose `status == ENABLED`. If no mod is enabled, select the first mod in the list.
- **FolderGridPanel._on_items_updated()**: Accept the `item_id_to_select` parameter (already passed by the signal but currently ignored) so the auto-selected mod also triggers the preview panel update, not just visual highlighting.

## Capabilities

### New Capabilities
*(none — this is a behavioral improvement to existing capabilities)*

### Modified Capabilities
*(none — no spec-level requirement changes; purely an implementation improvement)*

## Impact

- `app/viewmodels/mod_list_vm.py` — ~15 lines added to `_on_skeletons_loaded()` for the default selection logic
- `app/views/sections/foldergrid_panel.py` — ~5 lines changed in `_on_items_updated()` to handle the `item_id_to_select` parameter
