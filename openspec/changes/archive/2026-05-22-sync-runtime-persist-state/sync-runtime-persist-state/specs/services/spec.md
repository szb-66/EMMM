## ADDED Requirements

### Requirement: Disable-time runtime persist synchronization
When disabling a mod, `ModService` SHALL synchronize the mod's current runtime persist values from the corresponding game root `d3dx_user.ini` into the mod's own source `.ini` files before renaming the mod folder.

#### Scenario: Path-based persist value is written to source ini
- **WHEN** an enabled mod contains `global persist $swapvar = 0`, its source file maps to a path-based runtime key, and `d3dx_user.ini` contains that key with value `5`
- **THEN** disabling the mod updates the source `.ini` `global persist $swapvar` value to `5` before the folder is renamed

#### Scenario: Cycle options remain intact
- **WHEN** a persistent assignment has cycle options such as `$swapvar = 0,1,2,3,4,5`
- **THEN** disabling the mod updates only the `global persist` default and MUST NOT replace the cycle option list with the current value

#### Scenario: No runtime value leaves source ini unchanged
- **WHEN** a mod has persistent assignments but `d3dx_user.ini` does not contain matching runtime keys
- **THEN** disabling the mod does not change those source `.ini` defaults

### Requirement: Namespace persist key ownership
Disable-time synchronization SHALL use parsed persistent assignments to determine which runtime keys belong to the target mod, including namespace-derived keys.

#### Scenario: Namespace persist value is written to source ini
- **WHEN** a mod `.ini` declares `namespace = my_namespace`, contains `global persist $swapvar = 0`, and `d3dx_user.ini` contains `$\my_namespace\swapvar = 2`
- **THEN** disabling the mod updates that source `.ini` `global persist $swapvar` value to `2`

#### Scenario: Unowned runtime values are ignored
- **WHEN** `d3dx_user.ini` contains runtime keys that are not produced by parsing the target mod's persistent assignments
- **THEN** disabling the target mod MUST NOT write those unrelated runtime values into the target mod's source `.ini` files

### Requirement: Snapshot restore remains available
Disable-time source synchronization SHALL NOT remove the existing metadata snapshot and re-enable restore behavior.

#### Scenario: Runtime file is cleared after disable
- **WHEN** a mod is disabled after runtime persist values are captured and `d3dx_user.ini` is later cleared
- **THEN** re-enabling the mod restores the captured values from metadata into `d3dx_user.ini`

#### Scenario: Source synchronization and snapshot use same runtime value
- **WHEN** disabling a mod captures a runtime value for a persistent assignment
- **THEN** the value written to the source `.ini` default and the value stored in `persistent_state_snapshot` represent the same current runtime state

### Requirement: Source ini write safety
Disable-time source synchronization SHALL preserve existing `.ini` write safety behavior.

#### Scenario: Backup is created before modifying source ini
- **WHEN** disabling a mod requires changing a source `.ini` file and no backup exists
- **THEN** EMMM creates a one-time backup beside the source `.ini` before writing changes

#### Scenario: Source write failure is reported
- **WHEN** disabling a mod requires changing a source `.ini` file but the write fails
- **THEN** the disable operation reports failure rather than silently discarding the synchronization error
