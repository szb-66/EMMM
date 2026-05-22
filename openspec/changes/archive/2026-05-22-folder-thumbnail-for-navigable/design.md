## Context

当前 FolderGrid 中，文件夹根据 hydration 阶段是否包含 `.ini` 文件分为两类：

- **有 `.ini` → is_navigable=False → final mod**：扫描 preview 图片 → 缩略图
- **无 `.ini` → is_navigable=True → navigable folder**：直接返回，不扫描图片 → 文件夹图标

用户需要 navigable folder（如 Mod 合集文件夹）也能显示预览图片，同时保留导航功能。

## Goals / Non-Goals

**Goals:**
- Navigable folder 在 hydration 阶段扫描 preview 图片并写入元数据
- FolderGrid 卡片对有 preview 图片的 navigable folder 显示缩略图
- 预览面板（Preview Panel）正常展示 navigable folder 的图片 gallery
- 双击 navigable folder 仍可导航进入（行为不变）

**Non-Goals:**
- 不改动非 navigable folder（有 `.ini` 的 mod）的现有行为
- 不改动缩略图缓存服务（ThumbnailService）
- 不改动预览面板结构
- 不改动图片增删排序等管理操作

## Decisions

### Decision 1: hydration 阶段同时扫描图片和 .ini

**选择**：在 `hydrate_item()` 的 FolderItem 分支，将"扫描 `.ini`"和"扫描 preview 图片"解耦。先检查 `.ini` 决定 `is_navigable`，然后**无论结果**都扫描 preview 图片。

**原因**：这样 navigable folder 的 FolderItem 也能携带 `preview_images` 数据，下游所有模块（UI、缓存、预览面板）无需改动即可工作。

**替代方案考虑**：
- 在 UI 层额外请求图片扫描 → 需要新信号/异步逻辑，复杂度高
- 在独立的 post-hydration 阶段扫描 → 引入额外的生命周期状态，不必要

### Decision 2: info.json 元数据同步

**选择**：Navigable folder 的 preview 图片信息也写入 `info.json`，reconcile 逻辑与 final mod 分支一致。

**原因**：`add_preview_image`、`remove_preview_image`、`reorder_preview_images` 等操作都依赖 `info.json`，保持一致的元数据格式意味着这些操作对两种类型文件夹都无需改动。

### Decision 3: UI 层条件判断

**选择**：在 `set_data()` 中，当 `is_navigable is True` 且 `preview_images` 非空时：
- `default_icon_key` 设为 `"mod_placeholder"`（缩略图加载中的占位）
- `source_path_to_load` 设为 `preview_images[0]`
- `setMouseTracking(True)` 保持不变（双击仍可导航）

**原因**：复用现有的缩略图加载管线，零新代码。只有回退路径变为文件夹图标而不是 mod_placeholder。

## Risks / Trade-offs

- **无 preview 图片的 navigable folder 行为不变** → 仍然显示文件夹图标，无退化风险
- **info.json 创建** → 首次同步时如果文件夹无 `info.json` 则创建。现有 `_write_json` 已有处理
- **缩略图缓存键冲突** → 每个 FolderItem 的 `item_id` 基于相对路径的 SHA1，与类型无关，无冲突风险
- **预览面板 INI 配置区** → navigable folder 无 `.ini` 文件，INI 配置区显示空状态文案，预期行为
