## ADDED Requirements

### Requirement: Navigable folder 显示缩略图

可导航文件夹（不含 `.ini` 文件）如果有 `preview*` 命名的图片，SHALL 在 FolderGrid 卡片中显示缩略图。

#### Scenario: Navigable folder 有 preview 图片显示缩略图
- **WHEN** 一个 navigable folder 的目录下存在以 `preview` 开头的图片文件（`.png`/`.jpg`/`.jpeg`/`.webp`）
- **THEN** FolderGrid 卡片 SHALL 显示该图片的缩略图，而非文件夹图标

#### Scenario: Navigable folder 无 preview 图片显示文件夹图标
- **WHEN** 一个 navigable folder 的目录下没有以 `preview` 开头的图片文件
- **THEN** FolderGrid 卡片 SHALL 显示文件夹图标（现有行为不变）

#### Scenario: Navigable folder 双击导航行为保留
- **WHEN** 用户双击一个显示缩略图的 navigable folder
- **THEN** 系统 SHALL 导航进入该文件夹（双击行为不变）

#### Scenario: Navigable folder hydration 扫描 preview 图片
- **WHEN** 系统执行 `hydrate_item()` 处理一个 navigable folder
- **THEN** 系统 SHALL 扫描其目录下的 `preview*` 图片文件
- **THEN** 扫描结果 SHALL 写入 `preview_images` 字段
- **THEN** 图片列表 SHALL 与 `info.json` 同步（reconcile 逻辑）

### Requirement: Navigable folder 预览面板支持

选中 navigable folder 时，预览面板 SHALL 正常显示 Preview Images gallery，支持图片的增删排序操作。

#### Scenario: 选中 navigable folder 显示图片 gallery
- **WHEN** 用户选中一个有 preview 图片的 navigable folder
- **THEN** 右侧预览面板 SHALL 显示 Preview Images gallery
- **THEN** 用户 SHALL 可以添加、删除、排序图片

#### Scenario: 选中 navigable folder 显示 INI 空状态
- **WHEN** 用户选中一个 navigable folder（不含 `.ini` 文件）
- **THEN** Mod Configuration 区域 SHALL 显示 "No editable keybindings found in this mod." 空状态文案
