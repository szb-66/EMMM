## Context

PreviewPanel 右侧面板展示选中 mod 的详细信息。面板通过 `QSplitter` 布局，宽度随用户拖拽而变化（min 276px）。当前的 keybinding 编辑器使用固定宽度 160px 的输入框，导致：

- 面板宽度 > 400px 时：标签和输入框之间出现大量空白
- 面板宽度接近 min 时：160px 相对可用空间偏大

同时，KeyBinding 模型没有任何备注/说明字段，用户无法在应用中记录每个快捷键的作用。

## Goals / Non-Goals

**Goals:**
- Keybinding 输入框宽度自适应面板宽度（minimum 120px，弹性扩展）
- 每个 KeyBinding 支持一行文本备注，在 UI 中可见可编辑
- 备注持久化到 mod 文件夹下的 JSON 文件，不受 3DMigoto INI 重写影响
- 面板标题完整显示（移除 20 字符截断）

**Non-Goals:**
- 不改动缩略图区域布局（已自适应）
- 不改动描述编辑器布局（已自适应）
- 不修改 3DMigoto INI 文件格式（不向 INI 中写入注释）
- 不添加批量备注编辑功能

## Decisions

### Decision 1: 输入框布局策略（A2: MinExpand）

**选择**：将 `setFixedWidth(160)` + `QSizePolicy.Fixed` 替换为 `setMinimumWidth(120)` + `QSizePolicy.Expanding`，移除 `addStretch(1)` 让标签和输入框自然分布。

**布局变化**：
```
Before:  Label:  ════════════    [______160px______]
After:   Label:  [__120px~弹性__]
```

**原因**：最小改动达到响应式效果。标签使用 `Minimum` 策略保持紧凑，输入框用 `Expanding` 填充剩余空间。

**替代方案**：
- 比例布局（30%/70%）：在窄屏下标签可能被过度挤压
- 标签在上/输入框在下：垂直空间占用过多，不适合 keybinding 列表

### Decision 2: 备注存储格式与位置

**选择**：在 mod 文件夹根目录创建 `_emm_notes.json` 文件。

```json
{
  "version": 1,
  "keybinding_notes": {
    "d3dx.ini::Key_ToggleOutfit": "切换泳装样式",
    "d3dx.ini::Key_UIToggle": "隐藏UI截屏",
    "misc/extra.ini::Key_FreeCam": "自由视角开关"
  }
}
```

**Key 格式**：`相对INI路径::SectionName`（如 `d3dx.ini::Key_ToggleOutfit`）

**原因**：
- INI 注释方案存在 3DMigoto 重写覆盖的风险，且现有解析器不读注释
- JSON 方案与 3DMigoto 完全解耦，读写安全
- SectionName 跨会话稳定（不像 binding_id 是每次重新生成的 UUID）
- 放在 mod 文件夹内，备注随 mod 移动而携带
- `_` 前缀文件在大部分文件管理器中排序靠后，对用户干扰小
- JSON 格式可扩展，后续可添加其他元数据

### Decision 3: 备注存储服务

**选择**：新建 `app/services/note_service.py`，提供 `load_notes(mod_path)` / `save_notes(mod_path, notes)` / `update_note(mod_path, key, note)` 三个接口。

**原因**：与现有 `IniParsingService` 职责分离，备注与 INI 配置解耦。

### Decision 4: KeyBinding 模型变更

**选择**：KeyBinding dataclass 新增 `note: str = ""` 字段。

**原因**：View 层可以直接通过 `binding_data.note` 读写备注，不需要额外的查找表。`_on_ini_config_loaded` 时从 JSON 填充 note。

## Risks / Trade-offs

- **JSON 文件不存在**：首次打开时优雅降级（空字典），不报错
- **INI 文件重命名**：SectionName 不变无影响；INI 文件名变化时备注 key 会失效（可接受，极少发生）
- **多个 INI 文件同 section 名**：Key 包含文件名前缀，不会冲突
- **性能**：每次切换 mod 读取一次 JSON（~几 KB），无性能担忧
