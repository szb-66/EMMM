## 1. ViewModel: Default selection in _on_skeletons_loaded

- [x] 1.1 In `_on_skeletons_loaded()` (mod_list_vm.py), after the existing selection logic block (L792-828), add a new block: if `item_id_to_select is None` and `self.context == CONTEXT_FOLDERGRID` and `self.master_list` is non-empty, find the first item with `status == ModStatus.ENABLED` and set it as `item_id_to_select`, updating `last_selected_item_id` and `last_selected_item_name`. If no enabled item exists, use `self.master_list[0]`.

## 2. View: Handle item_id_to_select in FolderGridPanel

- [x] 2.1 In `FolderGridPanel._on_items_updated()` (foldergrid_panel.py), add `item_id_to_select: object = None` parameter to the method signature.
- [x] 2.2 After the grid rebuild loop, if `item_id_to_select` matches a widget in `_item_widgets`, call `self._on_grid_item_selected(widget.item_data)` to trigger the preview panel update.
