## ADDED Requirements

### Requirement: System SHALL handle `send2trash` timeout gracefully

When `send2trash` is called to move an image file to the recycle bin, the system SHALL enforce a timeout of no more than 5 seconds. If `send2trash` does not complete within the timeout, the system SHALL treat it as a failure and proceed to the fallback deletion path.

#### Scenario: send2trash completes within timeout

- **WHEN** `move_to_recycle_bin(image_path)` is called and the file is successfully moved to recycle bin within 5 seconds
- **THEN** the method returns `True`

#### Scenario: send2trash exceeds timeout

- **WHEN** `move_to_recycle_bin(image_path)` is called and `send2trash` does not complete within 5 seconds
- **THEN** the method returns `False` and logs a warning indicating the timeout

### Requirement: System SHALL fall back to direct deletion when recycle bin fails

If `send2trash` fails or times out, the system SHALL attempt to delete the image file directly using `os.remove`. The fallback SHALL be logged.

#### Scenario: Fallback deletion succeeds

- **WHEN** `send2trash` fails and `os.remove(image_path)` succeeds
- **THEN** the thumbnail operation continues normally and a toast notification with level "warning" is shown indicating "Image was permanently deleted (recycle bin unavailable)"

#### Scenario: Both send2trash and fallback fail

- **WHEN** `send2trash` fails and `os.remove(image_path)` also fails
- **THEN** the thumbnail operation returns an error result and the error toast shows "Failed to delete image: [reason]"

### Requirement: UI SHALL recover from hung thumbnail operations

The ViewModel SHALL enforce a 30-second timeout on thumbnail operations. If a Worker does not complete within 30 seconds, the system SHALL reset the loading state and show an error toast.

#### Scenario: Thumbnail operation completes within timeout

- **WHEN** a thumbnail Worker finishes within 30 seconds
- **THEN** the timeout timer is cancelled and normal result handling proceeds

#### Scenario: Thumbnail operation exceeds 30-second timeout

- **WHEN** a thumbnail Worker does not complete within 30 seconds
- **THEN** the system resets `thumbnail_operation_in_progress` to `False`, re-enables thumbnail buttons, shows an error toast "Thumbnail operation timed out", and sets a guard flag to ignore the late Worker result

### Requirement: User SHALL receive feedback on deletion errors

The system SHALL show a toast notification (InfoBar) for any deletion failure, timeout, or fallback path usage. The notification level SHALL be "warning" for fallback permanent deletion and "error" for complete failure.

#### Scenario: Fallback permanent deletion shows warning

- **WHEN** an image is permanently deleted (fallback path) instead of moved to recycle bin
- **THEN** a warning-level toast is shown describing that the image was permanently deleted

#### Scenario: Complete deletion failure shows error

- **WHEN** both recycle bin and direct deletion fail
- **THEN** an error-level toast is shown with the failure reason
