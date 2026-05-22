## Why

Deleting a mod preview image causes the application to freeze/hang because `send2trash` (via `system_utils.move_to_recycle_bin`) can block indefinitely on Windows when the file is locked, the recycle bin is corrupted, or antivirus is scanning. Since the background Worker never completes, `thumbnail_operation_in_progress` stays `True` permanently, disabling all thumbnail controls and leaving the UI in a stuck loading state with no feedback to the user.

## What Changes

- Add a configurable **timeout** to `move_to_recycle_bin` so the operation fails gracefully instead of hanging forever
- Add a **fallback** deletion path (direct `os.remove`) when `send2trash` fails or times out
- Show a **toast notification** when a deletion timeout/error occurs so the user understands what happened
- Add timeout handling in `_start_thumbnail_operation` so thumbnail operations can recover from hung workers
- Disable the delete button while the operation is in progress (already partially done via `thumbnail_operation_in_progress`)
- Add **loading state recovery** — if a worker exceeds a reasonable time, emit a timeout signal to reset the UI

## Capabilities

### New Capabilities
- `safe-image-deletion`: Robust deletion of mod preview images with timeout, fallback, and clear user feedback

### Modified Capabilities
<!-- No existing spec changes needed — this is an implementation robustness fix -->

## Impact

- `app/utils/system_utils.py` — `move_to_recycle_bin` gains timeout and fallback logic
- `app/utils/async_utils.py` — Worker may gain timeout support
- `app/viewmodels/preview_panel_vm.py` — `_start_thumbnail_operation` may gain timeout recovery
- `app/services/mod_service.py` — `_handle_image_removal` may gain fallback deletion path
- No new dependencies required; uses only stdlib + `send2trash` (existing dependency)
