## ADDED Requirements

### Requirement: Persistent state snapshot remains metadata fallback
Mod metadata files SHALL continue to store `persistent_state_snapshot` as a runtime restore fallback, even when source `.ini` defaults are synchronized during disable.

#### Scenario: Foldergrid mod stores snapshot in info json
- **WHEN** a foldergrid mod is disabled and matching runtime persist values are found
- **THEN** the mod's `info.json` contains `persistent_state_snapshot` with the captured normalized persist keys and values

#### Scenario: Objectlist item stores snapshot in properties json
- **WHEN** an objectlist item is disabled and matching runtime persist values are found
- **THEN** the item's `properties.json` contains `persistent_state_snapshot` with the captured normalized persist keys and values

### Requirement: Source ini defaults are not model fields
Synchronized source `.ini` persist defaults SHALL remain file content and SHALL NOT add mutable runtime state fields to `BaseModItem`, `ObjectItem`, or `FolderItem`.

#### Scenario: Item model remains immutable after synchronization
- **WHEN** disabling a mod synchronizes runtime persist values into source `.ini` files
- **THEN** the returned item model still represents the filesystem rename/status change through immutable dataclass replacement without adding runtime persist fields
