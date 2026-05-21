## ADDED Requirements

### Requirement: Cross-file persistent variable resolution

`get_runtime_persistent_assignments` SHALL build a complete folder-wide `global persist` declaration map before parsing individual `.ini` files, so that `[Key]` sections in any file are correctly matched against `global persist` declarations from any other file in the same mod folder.

#### Scenario: Persistent vars from sibling file are detected
- **WHEN** `SelectionMenu.ini` in a mod folder declares `global persist $BodyA = 1` and `Keys.ini` in the same folder contains `[KeyBodyAToggle]` with `$BodyA = 0,1`
- **THEN** `get_runtime_persistent_assignments` returns a `RuntimePersistAssignment` for `$BodyA` with `is_persistent = True`

#### Scenario: Non-persistent vars are not affected
- **WHEN** a `[Key]` section assigns a variable that is NOT declared as `global persist` in any file in the mod folder
- **THEN** the assignment's `is_persistent` flag remains `False`

### Requirement: Orphan persistent variable detection

`get_runtime_persistent_assignments` SHALL generate `RuntimePersistAssignment` entries for `global persist` variables that are declared but never referenced in any `[Key]` section, using the variable's declared default value as fallback.

#### Scenario: CommandList-only persist var is captured
- **WHEN** a mod declares `global persist $Corruption = 0` in `[Constants]` but `$Corruption` is only modified through `[CommandListCorruptionUp]` and `[CommandListCorruptionDown]` (not in any `[Key]` section)
- **THEN** `get_runtime_persistent_assignments` returns a `RuntimePersistAssignment` for `$Corruption` with its current runtime value from `d3dx_user.ini`

#### Scenario: Orphan var without runtime value is skipped
- **WHEN** a `global persist` variable is declared but never appears in `d3dx_user.ini`
- **THEN** `get_runtime_persistent_assignments` does NOT include it in the result

### Requirement: Backward-compatible parsing

`_parse_single_ini` SHALL accept an optional `folder_persistent_vars` parameter. When omitted, its behavior MUST be identical to the current implementation.

#### Scenario: Existing caller without folder_persistent_vars
- **WHEN** `load_keybindings_async` calls `_parse_single_ini` without the `folder_persistent_vars` parameter
- **THEN** parsing uses only the file-local `persistent_vars` set, exactly as before
