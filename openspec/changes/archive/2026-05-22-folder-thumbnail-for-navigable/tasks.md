## 1. Mod Service — hydration 阶段扫描 preview 图片

- [x] 1.1 在 `hydrate_item()` 中，当 folder 不含 `.ini` 文件时，扫描 `preview*` 图片文件
- [x] 1.2 实现 navigable folder 的 `info.json` reconcile 逻辑（与 final mod 分支一致的元数据同步）
- [x] 1.3 将扫描到的 preview 图片路径存入 FolderItem 的 `preview_images` 字段后返回

## 2. FolderGrid Widget — navigable folder 缩略图展示

- [x] 2.1 在 `set_data()` 的 `is_navigable is True` 分支中检查 `preview_images`
- [x] 2.2 有 preview 图片时设置 `source_path_to_load` 并走缩略图加载管线
- [x] 2.3 确保无 preview 图片时仍回退到文件夹图标

## 3. 验证

- [x] 3.1 确认有 preview 图片的 navigable folder 显示缩略图
- [x] 3.2 确认双击缩略图 navigable folder 仍可导航进入
- [x] 3.3 确认预览面板图片 gallery 正常工作
- [x] 3.4 确认无 preview 图片的 folder 行为不变
- [x] 3.5 确认 `info.json` 同步逻辑正确
