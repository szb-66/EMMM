# Keybinding Notes

**Responsibility:** Human-readable notes for 3DMigoto keybindings, persisted per-mod in `_emm_notes.json`.

### Requirement: Notes SHALL persist per-mod in `_emm_notes.json`

User notes for keybindings SHALL be stored in a file named `_emm_notes.json` inside the mod root folder. The file SHALL use the following schema:

```json
{
  "version": 1,
  "keybinding_notes": {
    "d3dx.ini::Key_ToggleOutfit": "note text"
  }
}
```

#### Scenario: Notes file does not exist

- **WHEN** a mod is selected for the first time and `_emm_notes.json` does not exist
- **THEN** the system SHALL treat it as an empty notes dictionary without error

#### Scenario: Notes file is corrupted

- **WHEN** `_emm_notes.json` exists but contains invalid JSON
- **THEN** the system SHALL fall back to an empty dictionary and log a warning

### Requirement: Notes key format SHALL use relative path and section name

Each note entry SHALL use a key in the format `<relative_ini_path>::<section_name>`:
- `relative_ini_path`: INI file path relative to the mod folder, using `/` separator
- `section_name`: the INI section name (e.g. `Key_ToggleOutfit`)
- Separator `::` ensures no conflict with valid section names

### Requirement: Notes SHALL be writable via NoteService

The system SHALL provide a `NoteService` with instance methods for notes persistence:

#### Scenario: Load notes

- **WHEN** `note_service.load_notes(mod_path)` is called
- **THEN** it returns a `Dict[str, str]` of key → note mappings, or empty dict on error

#### Scenario: Save notes

- **WHEN** `note_service.save_notes(mod_path, notes)` is called
- **THEN** the notes are atomically written to `_emm_notes.json` (temp file then rename)
- **AND** empty-string note values are filtered out before writing

#### Scenario: Update single note

- **WHEN** `note_service.update_note(mod_path, key, note)` is called
- **THEN** only that key is updated in `_emm_notes.json` and the full notes dict is returned

### Requirement: KeyBinding dataclass SHALL have a note field

The `KeyBinding` dataclass SHALL include a `note: str = ""` field and a `note_key(mod_path) -> str` method that generates the storage key.

### Requirement: KeyBindingWidget SHALL display a notes row

The UI SHALL display an editable notes row in each KeyBinding card, positioned below the section header and above the assignments. The field SHALL be a single-line `LineEdit`.

#### Scenario: Note editing marks config dirty

- **WHEN** the user types in the notes field
- **THEN** the system SHALL mark the configuration as dirty with `_notes_dirty = True`

### Requirement: Notes SHALL save with configuration

Note changes SHALL be persisted when the user clicks "Save Configuration". Notes-only changes SHALL save directly without invoking the INI writer.

#### Scenario: Notes and INI changes both dirty

- **WHEN** the user has edited both a note and an INI assignment, then clicks "Save Configuration"
- **THEN** the INI file is written first, then notes are written to `_emm_notes.json`

#### Scenario: Only notes changed

- **WHEN** the user has edited only a note field, then clicks "Save Configuration"
- **THEN** notes are saved to `_emm_notes.json` directly without touching the `.ini` file
