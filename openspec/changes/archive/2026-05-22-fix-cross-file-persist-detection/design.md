## Context

The disable-time runtime persist sync (`sync_runtime_persist_to_source` in `IniKeyParsingService`) works by:

1. Calling `get_runtime_persistent_assignments(folder_path)` which iterates each `.ini` file in the mod folder
2. For each file, calling `_parse_single_ini(file_path)` which parses `[Key]` sections and checks each assignment's variable against a **file-local** `persistent_vars` set
3. Only assignments where `is_persistent = True` are candidates for sync

The bug: `persistent_vars` is built per-file in `_parse_single_ini`. When a mod splits `global persist` declarations across files — e.g., all declarations in `SelectionMenu.ini` and all `[Key]` sections in `Keys.ini` — no file sees the complete set of persistent variables. The sync silently produces zero assignments.

Additionally, persistent variables that are only modified through `[CommandList]` sections (not `[Key]`) are never surfaced as assignments, so they're also missed even if in the same file.

## Goals / Non-Goals

**Goals:**

- Make `get_runtime_persistent_assignments` correctly detect persistent variables declared in any `.ini` file within the mod folder, regardless of which file contains the `[Key]` section
- Also detect `global persist` variables that never appear in any `[Key]` section (modified via `[CommandList]` only), using their declared default as the fallback current value
- Keep `_parse_single_ini` testable — the file-level parsing remains deterministic for existing unit tests

**Non-Goals:**

- Do not change the `_parse_single_ini` public signature used by `load_keybindings_async` — the shared `persistent_vars` set is only used in the `get_runtime_persistent_assignments` code path
- Do not change the snapshot/restore flow in `ModService`
- Do not change how `save_ini_changes` or `_update_persistent_constants_from_values` work

## Decisions

### Two-phase scan: pre-scan all files for `global persist`, then parse with shared set

`get_runtime_persistent_assignments` will be modified to:

1. **Phase 1 — Pre-scan**: Iterate all `.ini` files in the mod folder and collect every `global persist $var = value` declaration into a single folder-wide `persistent_vars` dict (variable → default value)
2. **Phase 2 — Parse with shared context**: Call `_parse_single_ini` for each file, passing the shared `persistent_vars` dict so assignments in `[Key]` sections from any file are correctly marked as persistent
3. **Phase 3 — Orphan persist vars**: For each `global persist` variable in the shared dict that never appeared in any `[Key]` section's assignments, synthesize a `RuntimePersistAssignment` directly using the variable's declared default value (looked up from `d3dx_user.ini` if available)

Alternative considered: Merge all `.ini` files into a single virtual file before parsing. Rejected because it would break line-level operations and make error messages misleading.

Alternative considered: Make `_parse_single_ini` always scan sibling files. Rejected — it would create hidden coupling and break the existing test pattern where a single `.ini` file is parsed in isolation.

### `_parse_single_ini` gains an optional `folder_persistent_vars` parameter

The existing signature `_parse_single_ini(file_path, game_root_path, runtime_persist_values)` gets an additional optional parameter. When `None` (the default for existing callers), behavior is identical to today. When provided, it's merged with (or overrides) the file-local `persistent_vars` set.

This preserves backward compatibility for:
- `load_keybindings_async` — doesn't need cross-file resolution
- Existing unit tests — pass `None` and get today's behavior

Alternative considered: New method `_parse_single_ini_with_shared_vars`. Rejected because it would duplicate 90% of the parsing logic.

### Phase 3 uses the shared var name→key mapping to match runtime values

For orphan `global persist` vars (not in any `[Key]` section), the persist key is computed the same way `_build_persist_key` does it. The normalized key is then looked up in `d3dx_user.ini`. If found, the runtime value is used; if not, the declaration default is kept (assignment is skipped — same as current skip behavior).

## Risks / Trade-offs

- **Performance**: Pre-scanning adds a second pass over all `.ini` files. Mitigation: the pre-scan is a single regex pass (no configparser), and the number of `.ini` files per mod is typically small (<20).
- **False positives**: A `global persist $var` in one file might share a name with a different variable in another file's `[Key]` section, but since they're in the same mod folder and share the same namespace/path context, this is architecturally correct.
- **Namespace collision**: The orphan persist var path generates keys using `_build_persist_key` (namespace-aware), so orphan vars in namespace-based mods are correctly keyed as `$\namespace\var`.
