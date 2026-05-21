## 1. Runtime Persist Mapping

- [x] 1.1 Add or expose a service helper that parses a mod folder's `.ini` files and returns persistent assignments with their source file, variable, current runtime value, and computed persist key.
- [x] 1.2 Ensure the helper reads runtime values from the game root `d3dx_user.ini` using `find_game_root_from_folder()` and existing normalized key handling.
- [x] 1.3 Cover namespace-derived persist keys so `namespace = ...` assignments map to `$\namespace\var` runtime keys.

## 2. Disable-Time Source Synchronization

- [x] 2.1 Add a `ModService` disable-time step that runs before folder rename and before the disabled prefix changes source paths.
- [x] 2.2 Update matched source `.ini` `global persist` lines with runtime values while preserving keybinding cycle option lists.
- [x] 2.3 Reuse or mirror existing one-time `.ini.backup` behavior before modifying source files.
- [x] 2.4 Keep existing `persistent_state_snapshot` save and restore behavior intact after adding source synchronization.
- [x] 2.5 Return a clear failure result if a required source `.ini` write fails before the disable rename completes.

## 3. Regression Coverage

- [x] 3.1 Add a path-based disable test proving `d3dx_user.ini` value is written back to the mod source `.ini`.
- [x] 3.2 Add a namespace-based disable test proving `$\namespace\var` runtime values update the correct source `global persist` line.
- [x] 3.3 Add a regression assertion that cycle options such as `$swapvar = 0,1,2` are not collapsed during disable-time synchronization.
- [x] 3.4 Add or update a test proving metadata `persistent_state_snapshot` is still written and can restore `d3dx_user.ini` after it is cleared.

## 4. Verification

- [x] 4.1 Run the targeted ini persistence test module.
- [x] 4.2 Run the broader relevant test suite if available in the local environment.
- [x] 4.3 Inspect any failed intermediate code from implementation attempts and remove dead or unused cleanup code before finishing.
