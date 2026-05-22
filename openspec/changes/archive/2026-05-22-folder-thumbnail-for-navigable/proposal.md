## Why

Mod合集文件夹（不含 `.ini` 文件的可导航文件夹）在缩略图网格中只能显示文件夹图标，无法展示预览图片。用户无法直观识别合集内容，且右侧预览面板也不显示图片管理模块。

## What Changes

- **Navigable folder 支持显示缩略图**：当可导航文件夹内存在 `preview` 命名的图片时，网格卡片显示缩略图而非文件夹图标
- **预览面板图片管理**：可导航文件夹选中后，预览面板正常显示 Preview Images gallery，支持添加/删除/排序图片
- **双击导航行为保留**：可导航文件夹即使显示缩略图，双击仍可以导航进入
- **info.json 元数据同步**：可导航文件夹的 preview_images 信息也写入 `info.json`，与普通 mod 行为一致

## Capabilities

### New Capabilities
- `folder-grid-thumbnail`: 缩略图网格中可导航文件夹的缩略图展示逻辑

### Modified Capabilities

（无现有 spec 需要修改）

## Impact

- `app/services/mod_service.py` — hydration 阶段为 navigable folder 扫描 preview 图片并写入 `info.json`
- `app/views/components/foldergrid_widget.py` — `set_data()` 中 `is_navigable is True` 分支增加 preview 图片检测
- 预览面板、缩略图服务、缓存系统均无需改动
