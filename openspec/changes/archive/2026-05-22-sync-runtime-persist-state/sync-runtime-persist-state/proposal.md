## Why

Users can change `global persist` mod state while the game is running, but that runtime state lives in the active XXMI `d3dx_user.ini` file rather than in the mod's own `.ini` defaults. When a mod is disabled, refreshed, or reloaded after the runtime file is cleared or regenerated, the mod can lose the last in-game state unless EMMM captures it before the disable operation.

## What Changes

- Before disabling a mod, read the current runtime persist values for that mod from the corresponding game root `d3dx_user.ini`.
- Synchronize matched runtime values back into the mod's own `.ini` files by updating `global persist $var = ...` defaults without collapsing cycle options.
- Keep the existing metadata snapshot behavior so re-enabling can still restore runtime values into `d3dx_user.ini`.
- Support both path-based persist keys and namespace-based persist keys when determining which runtime values belong to the mod.
- Preserve existing backup and file-structure safety expectations for `.ini` writes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `services`: `ModService` and `IniKeyParsingService` requirements change so disabling a mod synchronizes matched runtime persist values into source `.ini` files before renaming.
- `models`: metadata persistence expectations change to clarify that `persistent_state_snapshot` remains a runtime restore fallback while source `.ini` defaults can also be updated.

## Impact

- Affected services: `app/services/mod_service.py`, `app/services/Iniparsing_service.py`, `app/services/persist_utils.py`.
- Affected models/metadata: `info.json` and `properties.json` continue to store `persistent_state_snapshot`.
- Affected tests: `tests/test_ini_persistence.py` should cover path-based and namespace-based runtime state synchronization before disable.
- No new external dependencies or UI flows are expected.
