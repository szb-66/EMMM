## Context

EMMM already understands XXMI runtime persistence. `IniKeyParsingService` parses mod `.ini` files, detects `global persist` variables, builds normalized persist keys, and reads current values from the game root `d3dx_user.ini`. `ModService.toggle_status()` already snapshots matched runtime values to metadata before disabling a mod and restores that snapshot to `d3dx_user.ini` when the mod is re-enabled.

The missing behavior is source synchronization. If the game or launcher clears or regenerates `d3dx_user.ini` after a mod is disabled, the mod's own `.ini` defaults may still contain stale `global persist` values. Re-enabling or reloading can therefore fall back to old defaults unless the runtime state was also written back to the mod files before disable.

The game path stored in `Game.path` can point at an actual mods directory such as `GIMI/Mods` or `GIMI/Mods/character`, so all runtime persistence work must continue to locate the game root by walking ancestors until `d3dx_user.ini` or `d3dx.ini` is found.

## Goals / Non-Goals

**Goals:**

- Preserve the last in-game persist state when a mod is disabled and later refreshed or reloaded.
- Update only persist defaults that belong to the mod being disabled.
- Support path-derived persist keys and namespace-derived persist keys.
- Keep existing metadata snapshot/restore as a fallback layer.
- Reuse existing `.ini` parsing and backup behavior where possible.

**Non-Goals:**

- Do not add a new user-facing setting or UI workflow.
- Do not synchronize non-persistent local constants or arbitrary keybinding cycle options.
- Do not attempt to monitor game state continuously while the game is running.
- Do not change how enabled/disabled state is encoded in folder names.

## Decisions

### Synchronize during disable, before folder rename

The runtime state must be captured before `toggle_status()` renames the folder with the disabled prefix. At that point, source paths still match the enabled mod layout and existing key generation logic can normalize the path consistently.

Alternative considered: synchronize on app shutdown or launcher close. That would require process monitoring and still would not cover manual disable operations inside EMMM. The disable path is the most deterministic place because it is where state loss currently begins.

### Use parsed persist bindings as the ownership map

Path prefix matching is enough for normal persist keys such as `$\mods\character\some mod\merged.ini\swapvar`, but namespace keys such as `$\namespace\swapvar` cannot be attributed by path alone. The implementation should parse the mod's `.ini` files and use each persistent assignment's `persist_key` as the authoritative list of runtime keys owned by the mod.

Alternative considered: extend `_snapshot_persistent_state()` with more string matching. That would remain fragile for namespaces and duplicate variable names across files.

### Keep metadata snapshot as the runtime restore fallback

Writing source `.ini` defaults helps when `d3dx_user.ini` disappears or no longer contains the key, but the metadata snapshot still has value because re-enable can restore runtime overrides directly into `d3dx_user.ini`. The two mechanisms should be complementary:

```text
disable mod
  ├─ update source .ini global persist defaults
  └─ save persistent_state_snapshot

enable mod
  └─ restore persistent_state_snapshot to d3dx_user.ini
```

Alternative considered: replace snapshot with source `.ini` writes. That would weaken restore behavior when `d3dx_user.ini` still needs explicit runtime keys for F10 reload behavior.

### Preserve source file structure and backups

Source `.ini` updates should use the existing read-modify-write approach that updates `global persist $var = value` lines without changing the corresponding keybinding cycle list. A one-time `.backup` file should continue to be created before source modification.

Alternative considered: rebuild relevant `.ini` sections wholesale. Existing tests already protect against collapsing cycle options, so this would carry more risk than targeted updates.

## Risks / Trade-offs

- Runtime file is missing or stale -> Skip source synchronization and keep current disable behavior; no destructive fallback should be invented.
- Namespace keys collide across mods -> Use parsed assignments from the selected mod as the ownership map; if two mods intentionally share a namespace key, the current runtime value may be written to both when each is disabled.
- Source `.ini` file is read-only or locked -> Return a toggle failure before rename if synchronization cannot safely complete, or surface the write error consistently with existing `.ini` save failures.
- Multiple `.ini` files define the same persistent variable -> Match by each assignment's computed `persist_key`; path-based keys remain file-specific.
- File watcher sees internal writes -> Existing watched-refresh suppression around toggle operations should remain responsible for suppressing internal filesystem churn.

## Migration Plan

No data migration is required. Existing metadata snapshots remain valid. New source synchronization only runs during future disable operations.

Rollback is straightforward: remove the disable-time source synchronization call and leave existing snapshot/restore behavior intact.

## Open Questions

- Should a source sync failure block disabling the mod, or should EMMM disable the mod after saving the metadata snapshot and report a warning? The safer default is to block only when a source file was selected for update but could not be written.
