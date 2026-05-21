## Why

The disable-time runtime persist sync (`sync-runtime-persist-state`) silently fails for mods where `global persist` declarations and `[Key]` sections reside in different `.ini` files, or where persistent variables are modified exclusively through `[CommandList]` sections. This causes complete state loss when disabling/re-enabling such mods.

## What Changes

- `IniKeyParsingService._parse_single_ini` will accept a **shared, folder-wide** `persistent_vars` set instead of building one per-file
- `get_runtime_persistent_assignments` will pre-scan all `.ini` files in the mod folder to build a complete `persistent_vars` map before parsing individual files
- `get_runtime_persistent_assignments` will also generate `RuntimePersistAssignment` entries for `global persist` variables that are declared but never appear in any `[Key]` section, using their declared default values as fallback
- No API changes, no user-facing UI changes, no breaking changes

## Capabilities

### New Capabilities

- `cross-file-persist`: Correctly identify persistent variables across multiple `.ini` files within a mod folder, so that `[Key]` sections in one file can reference `global persist` declarations from another file

### Modified Capabilities

- `services`: Updated requirements for the IniKeyParsingService to support cross-file `persistent_vars` resolution

## Impact

- `app/services/Iniparsing_service.py`: Modified — `_parse_single_ini` signature and `get_runtime_persistent_assignments` logic
- `app/services/mod_service.py`: No change (caller interface unchanged)
- `tests/test_ini_persistence.py`: New test cases for cross-file persist detection
