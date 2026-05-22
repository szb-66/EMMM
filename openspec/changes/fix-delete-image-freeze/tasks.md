## 1. Timeout-safe `move_to_recycle_bin`

- [x] 1.1 Add `concurrent.futures`-based timeout wrapper around `send2trash` in `system_utils.py` with a 5-second timeout
- [x] 1.2 Add fallback to `os.remove` when `send2trash` fails or times out
- [x] 1.3 Log warning on timeout/fallback and return success/failure status

## 2. Thumbnail operation timeout recovery in ViewModel

- [x] 2.1 Add `_thumbnail_op_timer: QTimer` and `_thumbnail_op_timed_out: bool` to `PreviewPanelViewModel.__init__`
- [x] 2.2 In `_start_thumbnail_operation`, start a 30-second single-shot timer and reset guard flag
- [x] 2.3 Create `_on_thumbnail_operation_timeout` slot that resets `thumbnail_operation_in_progress` to False and shows error toast
- [x] 2.4 In result handlers (`_on_new_thumbnail_operation_finished`, `_on_thumbnail_operation_complete`), check `_thumbnail_op_timed_out` guard before processing, and stop the timer

## 3. Toast notifications for deletion errors

- [x] 3.1 In `_handle_image_removal` (mod_service.py), propagate toast-level information in the result dict for fallback vs. full failure scenarios
- [x] 3.2 In `_on_thumbnail_operation_complete` (preview_panel_vm.py), check for fallback/failure info in result and emit appropriate `toast_requested` signal
