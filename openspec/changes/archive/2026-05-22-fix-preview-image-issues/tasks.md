## 1. Fix cache invalidation bug

- [x] 1.1 Fix `ThumbnailService.invalidate_cache()` to always delete the L2 cache file `cache_dir/{item_id}.jpg` regardless of the `path` parameter

## 2. Replace FlipView with scrollable gallery

- [x] 2.1 Remove `self.flip_view.setFixedWidth(240)` from `ThumbnailSliderWidget._init_ui()`
- [x] 2.2 Replace `HorizontalFlipView` with a `QScrollArea` + horizontal widget layout for scrollable thumbnails
- [x] 2.3 Implement dynamic thumbnail sizing that fills available panel width (formula: ~1/3 to 1/4 of gallery width per thumbnail)
- [x] 2.4 Add click-to-select behavior with visual highlight on selected thumbnail
- [x] 2.5 Wire remove button to use the newly selected thumbnail index
- [x] 2.6 Wire drag-and-drop support to the new scrollable gallery

## 3. Add "Set as Cover" button

- [x] 3.1 Add `reorder_preview_images(item, new_order)` method to `ModService`
- [x] 3.2 Add `set_preview_image_as_cover(image_path)` method to `PreviewPanelViewModel`
- [x] 3.3 Add "Set as Cover" button to the thumbnail gallery control bar (top-right area)
- [x] 3.4 Hide the button when 0 or 1 images are present

## 4. Verify and clean up

- [ ] 4.1 Test removing an image and verify the grid thumbnail updates correctly
- [ ] 4.2 Test panel resize at various widths (min 276px to max width)
- [ ] 4.3 Test "Set as Cover" reorders images and grid thumbnail updates
- [ ] 4.4 Test add/paste/remove/clear-all still work with the new gallery
- [ ] 4.5 Test drag-drop image files into the new gallery
