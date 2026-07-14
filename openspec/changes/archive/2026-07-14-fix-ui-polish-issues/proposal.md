## Why

Five small UI polish issues hurt everyday usability: the folder grid pops in with a bottom-up animation on every in-role navigation (distracting and slow), pasted description text inherits external rich-text styles and renders black-on-black, long `.ini` config field labels push their inputs off the right edge of the preview panel, the Settings dialog opens with the Pivot highlight on "Mod Paths" but the stack still showing the "General" page, and the drag thumbnail is fully opaque so the cursor can't see what it's hovering. None are blockers; together they make the app feel rough.

## What Changes

- Replace the `PopUpAniStackedWidget` in `FolderGridPanel` with a plain `QStackedWidget` so.mods list load switches instantly with no pop-up animation.
- Set the description `TextEdit` to `setAcceptRichText(False)` so paste drops HTML styling and inherits theme color (fixes black-on-black).
- Make `.ini` config field labels word-wrap and give the row a label:field stretch ratio so long section/variable names wrap instead of pushing the input off-screen.
- Sync `SettingsDialog`'s `QStackedWidget` to the initial Pivot item on open so the visible page matches the highlighted tab.
- Render the drag thumbnail at 50% opacity so the cursor can see underlying content during internal mod drags.

## Capabilities

### New Capabilities
<!-- None — all changes modify existing view behavior. -->

### Modified Capabilities
- `views`: List-load animation removed; description paste becomes plain-text only; `.ini` config field labels wrap on overflow; settings tab/stack initial sync; drag pixmap rendered semi-transparent.

## Impact

- **Code:**
  - `app/views/sections/foldergrid_panel.py` — stack widget type change
  - `app/views/sections/preview_panel.py` — `TextEdit` accept-rich-text flag
  - `app/views/components/common/keybinding_widget.py` — label wrap + row stretch
  - `app/views/dialogs/settings_dialog.py` — initial stack sync
  - `app/views/components/foldergrid_widget.py` — drag pixmap opacity
- **APIs/Dependencies:** None added or removed; pure PyQt6/qfluentwidgets API usage.
- **Specs:** `views.md` gains requirements covering the five behaviors so regressions are detectable.
- **Risk:** Low — each change is localized and behavior-preserving aside from the targeted fix.