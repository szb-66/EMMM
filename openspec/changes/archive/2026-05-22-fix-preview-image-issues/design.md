## Context

The mod detail panel currently uses `HorizontalFlipView` (a `QListWidget` subclass from qfluentwidgets) for preview images. The widget is constrained to 240px fixed width, uses single-page flip navigation (prev/next buttons), and doesn't adapt when the user resizes the detail panel. The `ThumbnailService.invalidate_cache()` has a bug where passing a deleted source path skips L2 cache file deletion.

## Goals / Non-Goals

**Goals:**
- Replace the flip-view with a horizontally scrollable thumbnail gallery that adapts to panel width
- Fix the cache invalidation bug so deleted images don't persist in the grid thumbnail
- Add a "Set as Cover" button that reorders `preview_images` to put the current image first
- Keep all existing functionality: add/paste/remove/clear images, drag-drop, context menu

**Non-Goals:**
- Drag-and-drop reordering of images (future enhancement)
- Batch selection of multiple images
- Image zoom or full-screen viewer (separate feature)

## Decisions

**1. Replace `HorizontalFlipView` with a custom horizontal `QScrollArea` + `QHBoxLayout`**
- **Why:** `FlipView` is designed as a slideshow (one-at-a-time with scroll buttons), not a gallery. A `QScrollArea` with a horizontal layout of thumbnail widgets gives natural scrollbar behavior, allows multiple thumbnails visible at once, and follows standard gallery UX patterns.
- **Alternative considered:** Override `FlipView.resizeEvent` and `setItemSize` — possible but fighting the widget's design; the flip navigation behavior would still feel wrong.

**2. Compute thumbnail size dynamically from panel width**
- **Why:** The root complaint is that images don't adapt when the panel is resized. Each thumbnail's width should be a fraction of the available gallery width (e.g., `available_width / max_visible_count`, capped at a maximum size).
- **Formula:** `thumb_width = min(panel_width / items_per_row, max_thumb_width)` with `items_per_row` ≈ 3-4 and `max_thumb_width` ≈ 200px. Height maintains aspect ratio.

**3. `invalidate_cache` always clears the L2 cache by item_id**
- **Why:** The current code tries to delete the `path` argument (which is a source image path), not the actual cache file. The L2 cache is always `cache_dir/{item_id}.jpg` — never a source path. The method should ignore the `path` parameter for L2 deletion and always target the cache file.
- **Safety:** `get_thumbnail` re-generates the thumbnail from the new `preview_images[0]` on next access, so always clearing is safe.

**4. "Set as Cover" via list reorder**
- **Why:** The cover is implicitly `preview_images[0]`. Moving the selected image to index 0 is the simplest approach and doesn't require model changes. The UI refreshes via the existing `item_loaded` → `set_image_paths` chain.
- **Implementation:** Add `reorder_preview_images(item, new_order)` or `set_preview_image_as_cover(item, image_path)` to `ModService`. The ViewModel calls it, then refreshes.

## Risks / Trade-offs

- **[Layout breakage] → Mitigation:** The new scrollable gallery uses a different CSS/layout than FlipView. Test at various panel widths (min 276px+ per spec) to ensure no layout overflow.
- **[Image quality] → Mitigation:** Thumbnails at variable sizes may look different from the fixed 240px flip view. Use `Qt.SmoothTransformation` when scaling pixmaps.
- **[Scroll area vs FlipView features] → Mitigation:** The new gallery won't have built-in prev/next arrow buttons. The user can scroll naturally. Set `QScrollBar` policy to `AsNeeded` for horizontal scrollbar visibility.
