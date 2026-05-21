## MODIFIED Requirements

### Requirement: Namespace persist key ownership

Disable-time synchronization SHALL use parsed persistent assignments to determine which runtime keys belong to the target mod, including namespace-derived keys.

**MODIFICATION**: The parsed persistent assignments SHALL be collected from ALL `.ini` files in the mod folder using a folder-wide `global persist` declaration map, not file-local declarations alone.

#### Scenario: Namespace persist value from sibling file is written to source ini
- **WHEN** `SelectionMenu.ini` declares `namespace = JeanKnight` and `global persist $BodyA = 1`, and `Keys.ini` in the same folder contains `[KeyBodyAToggle]` with `$BodyA = 0,1`, and `d3dx_user.ini` contains `$\jeanknight\bodya = 0`
- **THEN** disabling the mod updates `SelectionMenu.ini`'s `global persist $BodyA` value to `0`
