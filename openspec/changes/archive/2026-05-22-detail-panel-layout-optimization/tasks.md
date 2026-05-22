## 1. NoteService — per-mod JSON 备注持久化

- [x] 1.1 新建 `app/services/note_service.py`，定义 `NOTES_FILE_NAME = "_emm_notes.json"`
- [x] 1.2 实现 `load_notes(mod_path: Path) -> dict[str, str]`
- [x] 1.3 实现 `save_notes(mod_path: Path, notes: dict[str, str])`（原子写入）
- [x] 1.4 实现 `update_note(mod_path: Path, key: str, note: str) -> dict[str, str]`（加载→修改→保存→返回完整 dict）

## 2. KeyBinding 模型 — 新增 note 字段

- [x] 2.1 `Iniparsing_service.py` 中 `KeyBinding` dataclass 新增 `note: str = ""` 字段
- [ ] 2.2 `_on_ini_config_loaded` 中将 NoteService 加载的备注填充到每个 `KeyBinding.note`

## 3. KeyBindingWidget — 响应式布局 + 备注行

- [x] 3.1 移除所有 `setFixedWidth(FIELD_WIDTH)` 和 `QSizePolicy.Fixed`，改为 `setMinimumWidth(120)` + `QSizePolicy.Expanding`
- [x] 3.2 `_create_row()` 中移除 `addStretch(1)`，让标签和输入框自然分布
- [x] 3.3 "备注"行 UI：在 `_init_ui()` 的 header 下方添加单行 `LineEdit`，绑定 `binding_data.note`，文本变化发 `value_changed` 信号（field_type="note"）
- [x] 3.4 `_create_row()` 的标签列改用 `setSizePolicy(Minimum, Preferred)` 保持紧凑
- [x] 3.5 `_create_trigger_row()` 和 `_create_assignment_row()` 同步移除固定宽度

## 4. PreviewPanel — 移除标题截断

- [ ] 4.1 移除 `preview_panel.py` 中 `_on_item_loaded` 的 20 字符截断逻辑（第 264-269 行），直接使用 `full_title`

## 5. PreviewPanelViewModel — 备注保存管线

- [x] 5.1 `__init__` 中注入 `NoteService`
- [x] 5.2 `on_keybinding_edited()` 新增处理 `field_type == "note"` 的分支
- [x] 5.3 `save_ini_config()` 中在 INI 保存成功后调用 `NoteService.save_notes()` 写出备注
- [x] 5.4 `_load_item()` 中解析 INI 完成后调用 `NoteService.load_notes()` 填充备注到 `KeyBinding.note`

## 6. 验证

- [ ] 6.1 确认面板宽度变化时输入框弹性伸缩，不溢出
- [ ] 6.2 确认备注行显示/编辑正常
- [ ] 6.3 确认备注随 "Save Configuration" 一起保存
- [ ] 6.4 确认切换 mod 后备注正确加载
- [ ] 6.5 确认标题完整显示，不再截断
- [ ] 6.6 确认 `_emm_notes.json` 文件生成且格式正确
