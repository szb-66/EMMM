## Why

The mod detail panel's preview image area has three issues: (1) the image width is hardcoded at 240px and doesn't adapt when the panel is resized, (2) deleting a preview image leaves the grid thumbnail showing the deleted image due to a cache invalidation bug, and (3) there's no way for users to choose which image appears as the mod's cover thumbnail.

## What Changes

- Replace `HorizontalFlipView` with a horizontal scrollable gallery layout that adapts to panel width
- Fix `ThumbnailService.invalidate_cache()` to properly clear the disk cache by item_id regardless of the path parameter
- Add a "Set as Cover" button to the thumbnail gallery that moves the current image to the front of `preview_images`
- Update the image list layout: remove fixed 240px width constraint, make thumbnails fill available panel width

## Capabilities

### New Capabilities
- `preview-gallery`: Scrollable thumbnail gallery with adaptive width, image reordering (set as cover), and responsive layout that fills the detail panel

### Modified Capabilities
- `thumbnail-service`: Fix cache invalidation — `invalidate_cache` must always clear the L2 cache file keyed by `item_id`, not by the deleted source path

## Impact

- `app/views/components/thumbnail_widget.py` — Major layout change (FlipView → scrollable gallery), add set-as-cover button
- `app/services/thumbnail_service.py` — Fix `invalidate_cache()` logic
- `app/models/mod_item_model.py` — No model changes needed (reordering preview_images list is sufficient)
- `app/viewmodels/preview_panel_vm.py` — May need method to reorder preview images
- `app/services/mod_service.py` — May need service method for reordering preview images
