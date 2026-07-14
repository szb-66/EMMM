## 1. Remove folder grid pop-up animation

- [x] 1.1 In `app/views/sections/foldergrid_panel.py`, change `self.stack = PopUpAniStackedWidget(self)` to `self.stack = QStackedWidget(self)`
- [x] 1.2 Add `QStackedWidget` to the `PyQt6.QtWidgets` import block in the same file
- [x] 1.3 Remove the now-unused `PopUpAniStackedWidget` import from the `qfluentwidgets` import block in the same file
- [x] 1.4 Verify the four `setCurrentWidget` call sites (`_on_path_changed`, `_on_items_updated`, `_on_empty_state_changed`, `_on_loading_started`) still compile and run

## 2. Force description editor to plain-text paste

- [x] 2.1 In `app/views/sections/preview_panel.py`, immediately after constructing `self.description_editor = TextEdit()`, call `self.description_editor.setAcceptRichText(False)`
- [x] 2.2 Confirm there is no existing rich-text authoring path that depends on `acceptRichText=True` (search for `setHtml`/`toHtml` usage on the editor — expect none)
- [x] 2.3 Verify `self.description_editor.setText(desc)` and `toPlainText()` round-trip still stores plain text

## 3. Make INI config field labels wrap on overflow

- [x] 3.1 In `app/views/components/common/keybinding_widget.py`, `_create_row`: set `lbl.setWordWrap(True)`
- [x] 3.2 Change the label's size policy from `QSizePolicy.Policy.Minimum` to `QSizePolicy.Policy.Preferred`
- [x] 3.3 Change `row.addWidget(lbl)` to `row.addWidget(lbl, 1)` so the label takes a bounded stretch share against the field's `FIELD_STRETCH`
- [x] 3.4 Confirm short-label rows do not wrap unnecessarily and long-label rows wrap the label while the field stays visible

## 4. Sync Settings dialog stack to initial tab

- [x] 4.1 In `app/views/dialogs/settings_dialog.py`, `_init_ui`, immediately after `self.pivot.setCurrentItem("games_tab")`, add `self.stack.setCurrentWidget(self.pages["games_tab"])`
- [x] 4.2 Launch the app and open Settings; confirm the visible page is the Games/Mod Paths page (table visible) and the Pivot highlight is on Mod Paths
- [x] 4.3 Click through every tab and confirm Pivot highlight and visible page stay in sync (existing `_switch_to_tab` path)

## 5. Render drag thumbnail at 50% opacity

- [x] 5.1 In `app/views/components/foldergrid_widget.py`, add `QPainter` to the `PyQt6.QtGui` import
- [x] 5.2 In `_build_drag_pixmap`, after the existing pixmap (`capped` or fallback from `self.grab()`), composite it onto a transparent `QPixmap` of the same size using `QPainter` with `setOpacity(0.5)`, return the composited pixmap
- [x] 5.3 Verify the original thumbnail label is not mutated (re-grab the same card still produces a full-opacity pixmap)
- [x] 5.4 Run the app, drag an internal mod, confirm underlying drop targets are visible through the thumbnail and the move cursor is preserved

## 6. Verification

- [x] 6.1 Run `pytest` (or the project's existing test command) — no view-layer tests break
- [x] 6.2 Run any lint/typecheck command provided by the project; fix new imports/unused-import warnings introduced by this change
- [ ] 6.3 Smoke test the five behaviors in a running app: in-role nav instant, paste plain text, long config label wraps, settings opens on correct tab, drag thumbnail translucent