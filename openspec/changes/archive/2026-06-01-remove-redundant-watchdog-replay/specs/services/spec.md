## MODIFIED Requirements

### Requirement: FileWatcherService directory watching

`FileWatcherService` SHALL monitor directories using `watchdog.Observer` with recursive watches and emit `directory_changed(key, changed_path)` via Qt signals for filesystem changes.

When a watch key is suppressed via `suppress_watch(key, duration_ms)`, all events for that key SHALL be silently dropped for the suppression duration. No events SHALL be queued or replayed when suppression expires.

#### Scenario: Suppressed events are dropped silently

- **WHEN** a watch key has an active suppression token
- **AND** a filesystem event occurs in the watched directory
- **THEN** the event SHALL be dropped without queuing
- **AND** no `directory_changed` signal SHALL be emitted for the suppressed event after suppression expires

#### Scenario: Events after suppression expire are processed normally

- **WHEN** a watch key's suppression token expires
- **AND** a new filesystem event occurs in the watched directory
- **THEN** `directory_changed` SHALL be emitted normally for the new event
