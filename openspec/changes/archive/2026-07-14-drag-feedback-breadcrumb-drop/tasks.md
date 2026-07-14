## 1. Drag source feedback (FolderGridItemWidget)

- [x] 1.1 In `app/views/components/foldergrid_widget.py` add imports: `QApplication`,
      `QDrag`/`QMimeData` (verify already imported), `QPoint`, `QPixmap`, `QBuffer`,
      `QIODevice`, `Qt.CursorShape`, and the `EMMM_MOD_MIME_TYPE` constant (verify
      import path `app.core.constants`).
- [x] 1.2 Add a `_build_drag_pixmap(self) -> QPixmap` helper: load the first entry of
      `self.item_data.get("preview_images")`; on success build a `QPixmap`, scale
      capped to 96 px on the long edge keeping aspect; on any failure (empty list,
      unreadable bytes, null pixmap) return `self.grab()` cast to `QPixmap`. Inline,
      no auxiliary class.
- [x] 1.3 In `mouseMoveEvent`, after building `mime` and before `drag.exec(...)`,
      call `pixmap = self._build_drag_pixmap(); drag.setPixmap(pixmap);
      drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))`.
- [x] 1.4 Replace the bare `drag.exec(Qt.DropAction.MoveAction)` call with
      `try: QApplication.setOverrideCursor(Qt.CursorShape.DragMoveCursor);
      drag.exec(Qt.DropAction.MoveAction) finally:
      QApplication.restoreOverrideCursor()`. Reset `self._drag_start_pos = None`
      before the try block.
- [ ] 1.5 Verify the existing mouse-threshold and MIME-set logic is unchanged;
      run the app, drag a mod card, confirm the thumbnail (or card snapshot)
      follows the cursor and the cursor is the move shape everywhere in the
      window. Confirm override restored after release / on Ctrl-C during drag.

## 2. Stable move cursor over existing drop targets

- [x] 2.1 In `app/views/components/foldergrid_widget.py` add
      `def dragMoveEvent(self, event):` to `FolderGridItemWidget` mirroring the
      existing `dragEnterEvent` acceptance: if
      `event.mimeData().hasFormat(EMMM_MOD_MIME_TYPE)` call
      `event.acceptProposedAction()`, else `super().dragMoveEvent(event)`.
- [x] 2.2 In `app/views/components/objectlist_widget.py` add
      `def dragMoveEvent(self, event):` with the same shape, mirroring its
      `dragEnterEvent`.
- [ ] 2.3 Run the app; drag a mod card slowly across another mod card and across
      a left-panel character row; confirm the move cursor stays stable across
      the entire widget area (no flicker back to the default arrow).

## 3. BreadcrumbWidget as ancestor drop target

- [x] 3.1 In `app/views/components/breadcrumb_widget.py` add imports:
      `QByteArray`, `QDragEnterEvent`, `QDragMoveEvent`, `QDropEvent`,
      `QDragLeaveEvent` (or use `QEvent` base if preferred by project style),
      `Qt`, and `from app.core.constants import EMMM_MOD_MIME_TYPE`.
- [x] 3.2 Add `drop_requested = pyqtSignal(str, object)` next to
      `navigation_requested`. Initialize `self._hover_index: int | None = None`
      in `__init__`.
- [x] 3.3 Call `self.setAcceptDrops(True)` at the end of `_init_ui` (on the
      `BreadcrumbWidget`, not on the inner `BreadcrumbBar`).
- [x] 3.4 Add `dragEnterEvent(self, event)`: if
      `event.mimeData().hasFormat(EMMM_MOD_MIME_TYPE)` call
      `event.acceptProposedAction()`, else `super().dragEnterEvent(event)`.
- [x] 3.5 Add `_clear_hover(self)` helper: if `_hover_index` is in range of
      `self.breadcrumb.items`, set `item.isHover = False; item.update()`; set
      `self._hover_index = None`.
- [x] 3.6 Add `dragMoveEvent(self, event)`: only act when MIME has
      `EMMM_MOD_MIME_TYPE`. Map cursor pos into `self.breadcrumb`:
      `pos = self.breadcrumb.mapFrom(self, event.position().toPoint())`.
      Iterate `enumerate(self.breadcrumb.items)`; skip `ElideButton`
      (`i != isinstance(item, BreadcrumbItem)` not needed — use the
      `BreadcrumbItem` type check import, or compare
      `isinstance(item, BreadcrumbItem)`); skip `not item.isVisible()`. Pick the
      first item whose `item.geometry().contains(pos)` is true. If found and
      `index < len(self._segment_paths) - 1` (strict ancestor): clear previous
      hover via `_clear_hover`, set `item.isHover = True; item.update()`,
      store `self._hover_index = index`, `event.acceptProposedAction()`. If
      found but it's the last segment, or no hit: `_clear_hover()`,
      `event.ignore()`. Non-internal MIME: `super().dragMoveEvent(event)`.
- [x] 3.7 Add `dragLeaveEvent(self, event)`: call `self._clear_hover()` then
      `super().dragLeaveEvent(event)`.
- [x] 3.8 Add `dropEvent(self, event)`: if MIME lacks `EMMM_MOD_MIME_TYPE`,
      `super().dropEvent(event)` and return. Decode
      `dropped_id = bytes(event.mimeData().data(EMMM_MOD_MIME_TYPE)).decode("utf-8")`.
      If `self._hover_index is not None` and `0 <= _hover_index <
      len(self._segment_paths)` and `_hover_index < len(self._segment_paths) - 1`:
      emit `self.drop_requested.emit(dropped_id, self._segment_paths[self._hover_index])`,
      call `event.acceptProposedAction()`. Else `event.ignore()`. Always call
      `self._clear_hover()` at the end.
- [x] 3.9 Add `# ponytail: linear scan over ≤ ~8 breadcrumb segments per
      dragMoveEvent; if deep folders ever push this higher, precompute a
      [(rect, index)] list in _build_from_path` comment above the loop.
- [x] 3.10 Sanity verify: while dragging, the breadcrumb item pointers
      (`self.breadcrumb.items`) are the same widgets whose `isHover` we toggle
      (compare against `BreadcrumbBar.items` in the installed qfluentwidgets
      `bindGE` walkthrough); adjust if accesses differ.

## 4. Panel wiring

- [x] 4.1 In `app/views/sections/foldergrid_panel.py` locate the
      `BreadcrumbWidget` instantiation (~line 147) and store the reference on
      `self.breadcrumb_widget` (capture the existing local the panel already
      has; only add storage if not already stored).
- [x] 4.2 Connect `self.breadcrumb_widget.drop_requested.connect(
      self.view_model.move_item_to_folder)` near the existing
      `navigation_requested` connection (~line 232-234).
- [x] 4.3 Confirm `ModListViewModel.move_item_to_folder(item_id, path)` signature
      is `(str, object)` compat → read
      `app/viewmodels/mod_list_vm/_crud_mixin.py:20-47` and adjust the connection
      only if signatures differ.
- [x] 4.4 Leave the panel's external-file `dragEnterEvent`/`dropEvent`
      untouched; verify via a manual drop of a `.zip` onto the panel that import
      still works.

## 5. Verification

- [ ] 5.1 Run the app, navigate into a character's nested folder so the
      breadcrumb shows root > sub > current. Start a drag from a mod card in the
      current folder.
- [ ] 5.2 Drag over the root segment and an ancestor (middle) segment: each
      lights up with the hover style; the move cursor is shown. Drag over the
      current (last) segment: highlight clears and the forbidden cursor shows.
- [ ] 5.3 Release over an ancestor segment: the mod moves into that class's
      directory; the grid reloads at the same navigated folder and the mod's
      card no longer appears there.
- [ ] 5.4 Drag the same card out of the breadcrumb into empty space: highlight
      clears on leave; cursor is forbidden over the gap and move over the
      breadcrumb's ancestor segments again on re-entry.
- [ ] 5.5 Regression: drag an external `.zip` from Explorer onto
      `FolderGridPanel` background — import dialog still appears; drag an image
      file onto the preview `ThumbnailWidget` — still attaches as preview.
- [ ] 5.6 Smoke: start a drag and immediately close the window with Alt+F4 /
      Ctrl-C in the console — confirm no orphan `setOverrideCursor` survives
      (cursor restored by the `finally`).
- [ ] 5.7 If a project formatter / type checker is configured (ruff / mypy),
      run it on the three modified files and fix any new findings.