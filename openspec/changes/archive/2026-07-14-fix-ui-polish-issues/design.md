## Context

The five fixes target view-layer behaviors documented in `openspec/specs/views.md`. All live in the PyQt6/qfluentwidgets view components; none touch ViewModels, services, or persistence. Current state:

- `FolderGridPanel.stack` is a `PopUpAniStackedWidget` whose `deltaY=76` pop-up animation plays on every page switch (placeholder ↔ scroll_area ↔ empty_state ↔ shimmer), making in-role navigation feel laggy.
- `PreviewPanel.description_editor` is a qfluentwidgets `TextEdit` (subclass of `QTextEdit`) with default `acceptRichText=True`, so pasted HTML keeps its inline color styles — on a dark theme that yields black text on a black background.
- `KeyBindingWidget._create_row` gives the field label a `Minimum` size policy with no word-wrap and adds it with no stretch, so a long section/variable name expands the label and squeezes the input off the right edge of the narrow preview panel.
- `SettingsDialog._init_ui` calls `self.pivot.setCurrentItem("games_tab")` to highlight the Mod Paths tab, but never calls `self.stack.setCurrentWidget(...)`, so the `QStackedWidget` keeps its default (first-added = `general_tab`) page — a tab/content mismatch until the user clicks a tab.
- `FolderGridItemWidget._build_drag_pixmap` returns an opaque `QPixmap`; during internal drags the cursor can't see what's underneath, making drop targeting hard.

## Goals / Non-Goals

**Goals:**
- Make in-role mod list load instantaneous with no pop-up animation.
- Force description paste to plain text so it always renders legibly on the current theme.
- Keep long `.ini` config field labels readable without pushing their inputs off-screen.
- Make the Settings dialog's visible page match the highlighted tab on first open.
- Let the drag thumbnail show underlying content at 50% opacity.

**Non-Goals:**
- Re-architecting any panel or introducing new ViewModel signals.
- Adding a "paste without formatting" toggle or keyboard shortcut — plain-text is the only mode now.
- Adding user-facing settings for animation speed, wrap threshold, or drag opacity.
- Touching the external-file drag-and-drop import path or its pixmap (only the internal `EMMM_MOD_MIME_TYPE` drag pixmap changes).

## Decisions

### 1. Replace `PopUpAniStackedWidget` with `QStackedWidget` in `FolderGridPanel`

**Choice:** Swap `self.stack` to a plain `QStackedWidget`.
**Rationale:** The panel doesn't connect to `aniFinished`/`aniStart` and doesn't rely on the animation for any logic. A plain stack switches synchronously with no `QPropertyAnimation` overhead. The existing `setCurrentWidget` calls in `_on_path_changed`, `_on_items_updated`, `_on_empty_state_changed`, and `_on_loading_started` keep working unchanged.
**Alternatives considered:**
- Keep `PopUpAniStackedWidget` and call `setCurrentWidget` with `needPopOut=False` — but constructor-coupled `deltaY=76` and the per-`addWidget` `PopUpAniInfo` still cost setup complexity and offer no benefit when no animation is wanted anywhere in this panel.
- Subclass to disable animations — extra file for zero gain.

### 2. Set `description_editor.setAcceptRichText(False)`

**Choice:** One-line flag flip in `PreviewPanel._init_ui` right after constructing the `TextEdit`.
**Rationale:** `QTextEdit.setAcceptRichText(False)` makes `insertFromMimeData` strip HTML and paste plain text, so pasted content inherits the widget's stylesheet color (theme-aware). Fixes black-on-black without a custom `MimeData` filter or a paste handler. The editor already stores/loads description as plain text via `toPlainText()`/`setText()`, so storage is unaffected.
**Alternatives considered:**
- Override `insertFromMimeData` to call `setText(mimeData.text())` — more code for the same effect, and `setAcceptRichText(False)` already handles it natively.
- Strip styles via stylesheet `QTextEdit { color: ... }` — doesn't help, pasted inline HTML color overrides the stylesheet.

### 3. Word-wrap `.ini` config field labels with a row stretch ratio

**Choice:** In `KeyBindingWidget._create_row`, set `lbl.setWordWrap(True)`, change the label's size policy to `Preferred` (allows shrink), and add it with `row.addWidget(lbl, 1)` against `field` at `FIELD_STRETCH=3`. Keep the existing row's contentsMargins/spacing.
**Rationale:** `QHBoxLayout` honors per-widget stretch; giving the label a non-zero stretch lets it claim a bounded fraction of the row width, after which `setWordWrap(True)` wraps the text onto extra lines instead of expanding horizontally. Field stays visible within its 3/4 share.
**Alternatives considered:**
- Switch the row to a `QFormLayout` with `WrapAllRows` — bigger layout change, wider pixel footprint for short labels, and risks disrupting the trigger-row styling consistency.
- Cap label with `setMaximumWidth` — brittle at different panel widths, doesn't reflow when the splitter resizes.
- Use `ElideRight` on the label — loses information (the user can't read the full variable name); wrapping preserves it.

### 4. Sync `SettingsDialog` stack to the initial Pivot item

**Choice:** In `SettingsDialog._init_ui`, immediately after `self.pivot.setCurrentItem("games_tab")`, add `self.stack.setCurrentWidget(self.pages["games_tab"])`.
**Rationale:** `Pivot.setCurrentItem` only updates the highlighted route key; it doesn't touch the linked `QStackedWidget`. The stack defaults to the first-added widget (`general_tab`), so a highlighted tab and visible page drift apart until a tab click routes through `_switch_to_tab`. One explicit `setCurrentWidget` removes the drift.
**Alternatives considered:**
- Call `self._switch_to_tab("games_tab")` instead — works but couples initial state to the click handler; the inline `setCurrentWidget` is clearer about intent and avoids firing the lambda indirection.
- Reorder `_create_*_tab` calls so `games_tab` is added first — fragile, breaks the natural General→Games ordering in the Pivot strip.

### 5. Render the drag thumbnail at 50% opacity

**Choice:** In `FolderGridItemWidget._build_drag_pixmap`, after producing the capped pixmap (or the `self.grab()` fallback), compose it onto a transparent `QPixmap` of the same size using a `QPainter` with `setOpacity(0.5)`. Return the composited pixmap.
**Rationale:** `QDrag.setPixmap` accepts any `QPixmap` with alpha; a semi-transparent pixmap lets the cursor see underlying drop targets while still showing what's being dragged. 50% is a perceptible but not ghostly level that matches common OS drag-feedback conventions. Compositing (rather than mutating the source) keeps the original thumbnail intact for re-use.
**Alternatives considered:**
- `QPixmap.setAlphaChannel` via a gradient mask — opaque code; `QPainter.setOpacity` is one line on the draw path.
- Lower opacity (e.g. 30%) — risks the thumbnail looking absent on dark cards; 50% holds up across themes.

## Risks / Trade-offs

- **[Loss of pop-up animation might mask loading latency]** → The shimmer frame still covers the loading window via `_on_loading_started`/`_on_loading_finished`; removing only the page-switch animation doesn't hide load time, it just removes the extra slide after the shimmer clears.
- **[Plain-text paste drops intentional formatting]** → Descriptions were already stored and displayed as plain text (`toPlainText()`); users weren't intentionally authoring rich text. No migration needed.
- **[Wrapped label rows get taller than single-line rows]** → Visual row-height variation within a `KeyBindingWidget` is acceptable in a scrollable preview panel; the alternative (truncation) is worse for usability.
- **[Stack/`QStackedWidget` swap removes an upstream class import]** → Keep the `PopUpAniStackedWidget` import removed from `foldergrid_panel.py` to avoid lint warnings; no other module imports it from here.
- **[50% opacity on a near-black thumbnail on a dark theme can look invisible]** → Edge case; the fallback still shows a recognizable card shape and the move cursor stays on. If reported, the opacity constant is a one-line knob.

## Migration Plan

No data migration, no API breaks, no config-flag introduction. Single PR delivering all five view-layer edits. Rollback = revert the PR. Each change is independently revertible if one turns out wrong.

## Open Questions

None — all five target sites, behaviors, and constants are pinned down in the prior diagnostic pass.