## Context

When the user clicks "Remove Current Image" in the thumbnail slider, the following happens:

1. A `MessageBox` confirmation dialog appears (via qfluentwidgets `MessageBox.exec()` — synchronous, blocks main thread)
2. On confirm, `remove_thumbnail()` spawns a `Worker` via `QThreadPool` to run `mod_service.remove_preview_image()`
3. Inside, `_handle_image_removal()` calls `system_utils.move_to_recycle_bin()` which delegates to `send2trash`
4. **Problem**: `send2trash` on Windows can hang indefinitely if the file is locked, the recycle bin is corrupted, or antivirus is scanning
5. Since the Worker never completes, `thumbnail_operation_in_progress(True)` never resets, permanently disabling all thumbnail buttons

The `MessageBox` also carries risk: as a `QDialog.exec()`, it blocks the main event loop. If the dialog fails to render (qfluentwidgets uses `MaskDialogBase` with `FramelessWindowHint` + `WA_TranslucentBackground`), the main window appears frozen with no visible dialog.

## Goals / Non-Goals

**Goals:**
- `send2trash` call SHALL have a timeout so it cannot block indefinitely
- When recycle bin deletion fails/times out, a fallback path SHALL attempt direct file deletion
- UI SHALL recover from stuck thumbnail operations (via timeout recovery)
- User SHALL receive a toast notification when deletion fails
- Thumbnail image files SHALL be deleted from disk even if recycle bin is unavailable

**Non-Goals:**
- Replacing `send2trash` with a different library entirely
- Changing the image preview UI layout or behavior
- Fixing the `MessageBox` rendering issue (out of scope — the main fix is eliminating the blocking scenario)
- Adding undo/trash restore functionality

## Decisions

### Decision 1: Thread-based timeout for `send2trash`

**Choice**: Wrap `send2trash` in a `concurrent.futures.ThreadPoolExecutor` with a 5-second timeout, rather than using `QThread` + `QTimer` or `QFutureWatcher`.

**Rationale**: `concurrent.futures` provides a clean, stdlib-only timeout mechanism. It does not require Qt dependencies or event-loop integration for the timeout. The existing `Worker`/`QThreadPool` infrastructure handles the outer thumbnail operation; the timeout only needs to protect the `send2trash` call itself.

**Alternatives considered**:
- **`QTimer` + `QThread`**: More Qt-idiomatic but adds complexity for a simple timeout.
- **`QFutureWatcher` + `QtConcurrent.run`**: Would require PyQt6's `QtConcurrent` which may not be available in all installations.
- **Raise `send2trash` timeout via signal**: Not supported by the `send2trash` library.

### Decision 2: Fallback to `os.remove` on recycle bin failure

**Choice**: When `send2trash` fails or times out, fall back to `os.remove(path)` to delete the file directly (permanent deletion).

**Rationale**: Permanent deletion is better than leaving the file undeleted and the app stuck. The user already confirmed deletion in the dialog. If the recycle bin is unavailable, direct deletion is the only reliable way to proceed.

**Trade-off**: The user loses the ability to restore from recycle bin on the fallback path. This is acceptable because:
- The operation is user-initiated with confirmation
- The primary path (`send2trash`) is still attempted first
- A toast notification informs the user when fallback is used

### Decision 3: Worker-level timeout for thumbnail operations

**Choice**: Add a `QTimer`-based timeout in `_start_thumbnail_operation` that fires after 30 seconds if the Worker has not completed.

**Rationale**: Even with the `send2trash` timeout, other unforeseen issues could block the Worker. A 30-second timeout ensures the UI always recovers. The timer is started on the main thread and connected to a recovery slot that resets `thumbnail_operation_in_progress` and shows an error toast.

## Risks / Trade-offs

- **Fallback deletes permanently**: If the user expected recycle bin recovery, the fallback `os.remove` is irreversible. Mitigation: log the fallback usage and show a toast so the user knows.
- **Timeout race condition**: The timer could fire after the Worker completes but before the result signal is processed. Mitigation: use a guard flag (`_thumbnail_op_timed_out`) checked in both the timeout handler and the result handler.
- **send2trash on non-Windows platforms**: The timeout is platform-agnostic; it protects macOS and Linux too where `send2trash` could also block (e.g., network drives, permission prompts).
