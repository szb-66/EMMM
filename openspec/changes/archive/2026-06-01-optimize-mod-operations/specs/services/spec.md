# Services Layer

**Responsibility:** Services encapsulate all business logic and I/O.

## MODIFIED Requirements

### FileWatcherService: Watch directories recursively
FileWatcherService SHALL monitor directory changes using recursive watches so that modifications to nested files and subdirectories are detected.

#### Scenario: Deleting nested subfolder triggers refresh
- **WHEN** a mod folder contains a subdirectory `textures/` and the user deletes `textures/` via Windows Explorer
- **THEN** FileWatcherService SHALL emit `directory_changed` with the key for the watched directory
- **AND** the UI SHALL refresh to reflect the deletion

#### Scenario: Adding file in nested folder triggers refresh
- **WHEN** a mod folder contains a subdirectory and the user adds a new file to that subdirectory
- **THEN** FileWatcherService SHALL emit `directory_changed`

### FileWatcherService: External events preserved during suppression
When a suppression token is active, the service SHALL queue filesystem events that do not match the known internal operation pattern. Events for the same `src_path` within the suppression window SHALL be collapsed. After the suppression token clears, any queued events SHALL be replayed.

#### Scenario: External deletion during suppression is not lost
- **WHEN** the user toggles a mod (triggering 5-second suppression) and then deletes a different mod's folder via Explorer within those 5 seconds
- **THEN** the deletion event SHALL be queued, not dropped
- **AND** after the suppression window clears, the UI SHALL refresh to reflect the deletion

#### Scenario: Duplicate events during suppression are collapsed
- **WHEN** a single external operation fires multiple watchdog events for the same `src_path` during suppression
- **THEN** only one event for that `src_path` SHALL be queued
- **AND** after suppression clears, the UI SHALL refresh once for that `src_path`

### ModService: Toggle status avoids full directory reload
When a single item's status is toggled, ModService SHALL return the updated item model. The ViewModel SHALL replace the item in its internal lists in-place without triggering a full directory re-scan.

#### Scenario: Toggling one mod does not re-scan the directory
- **WHEN** the user toggles a single mod from enabled to disabled
- **THEN** the item SHALL be updated in-place in the master list
- **AND** no `os.scandir` call SHALL be made for the parent directory
- **AND** the foldergrid view SHALL update only the toggled item's visual representation
