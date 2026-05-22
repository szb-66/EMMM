## Why

当前 Mod 详情面板（PreviewPanel）的 .ini 配置编辑区存在两个布局问题：
1. **输入框固定宽度 160px** — 面板宽时中间留大片空白，面板窄时 160px 可能溢出，无法利用可用空间
2. **无法为 keybinding 添加备注/说明** — 用户无法记录某个快捷键的功能意图（如"切换泳装"），对含大量 keybinding 的复杂 mod 尤其不便

## What Changes

- **Keybinding 编辑区布局响应式改造**：输入框从 `Fixed(160px)` 改为 `Minimum(120px) + Expanding`，标签和输入框同行自然分布，充分利用面板宽度
- **Keybinding 备注功能**：每个 KeyBinding 支持添加一行文本备注，存储在 mod 文件夹下的独立 JSON 文件中
- **面板标题移除 20 字符截断**：利用 wordWrap 自适应显示完整标题

## Capabilities

### New Capabilities
- `keybinding-notes`: keybinding 备注的持久化与 UI 展示

### Modified Capabilities
- `views.md` — PreviewPanel / KeyBindingWidget 的布局策略更新

## Impact

- `app/views/components/common/keybinding_widget.py` — 布局策略从 Fixed 改为 MinExpand，增加备注行 UI
- `app/views/components/common/ini_file_group_widget.py` — 无改动（容器自适应）
- `app/views/sections/preview_panel.py` — 移除标题 20 字符截断
- `app/services/Iniparsing_service.py` — KeyBinding dataclass 可能新增 note 字段
- **新文件**: per-mod JSON metadata 读写逻辑（建议放在 `app/services/note_service.py`）
