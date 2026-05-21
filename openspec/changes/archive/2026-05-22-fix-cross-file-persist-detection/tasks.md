## 1. Pre-scan Phase — Folder-wide persistent_vars collection

- [x] 1.1 Add a helper method `_collect_folder_persistent_vars(folder_path)` that iterates all `.ini` files and returns a `dict[str, str]` mapping variable name → declared default for every `global persist` declaration found at file level or inside `[Constants]` section
- [x] 1.2 Ensure the pre-scan handles both file-level `global persist $var = value` and `[Constants]` section declarations (same regex logic as `_parse_single_ini`)

## 2. Core Implementation — Cross-file resolution in get_runtime_persistent_assignments

- [x] 2.1 Add optional `folder_persistent_vars: dict[str, str] | None = None` parameter to `_parse_single_ini`; when provided, merge it into (or override) the file-local `persistent_vars` set
- [x] 2.2 Modify `get_runtime_persistent_assignments` to run the pre-scan phase before the file-iteration phase, then pass the shared dict to each `_parse_single_ini` call
- [x] 2.3 Add Phase 3 logic in `get_runtime_persistent_assignments`: for each `global persist` variable in the shared dict that was NOT matched by any `[Key]` section assignment, synthesize a `RuntimePersistAssignment` using `_build_persist_key` and lookup in `d3dx_user.ini`

## 3. Testing

- [x] 3.1 Add test: `global persist` in file A, `[Key]` section referencing same var in file B — verify `RuntimePersistAssignment` is returned with correct `persist_key` and `is_persistent`
- [x] 3.2 Add test: `global persist` var only referenced in `[CommandList]` (orphan) — verify `RuntimePersistAssignment` is returned with runtime value from `d3dx_user.ini`
- [x] 3.3 Add test: orphan var without matching runtime key — verify it is NOT returned
- [x] 3.4 Add test: `_parse_single_ini` without `folder_persistent_vars` parameter — verify existing behavior is unchanged
- [x] 3.5 Run full `test_ini_persistence.py` suite to confirm no regressions

## 4. Verification

- [x] 4.1 Run the targeted ini persistence test module
- [x] 4.2 Validate against the JeanCorruptedKnight1 mod structure by inspecting that all 235 `$\jeanknight\...` runtime keys produce corresponding `RuntimePersistAssignment` entries
