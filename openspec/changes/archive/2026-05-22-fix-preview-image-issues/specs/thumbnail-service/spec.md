## MODIFIED Requirements

### Requirement: Cache invalidation clears both L1 and L2 caches
The system SHALL remove cached thumbnails from both L1 (memory) and L2 (disk) caches when invalidated. The L2 cache file is always identified by `item_id`, never by source image path.

#### Scenario: Invalidate cache clears disk cache by item_id
- **WHEN** `invalidate_cache(item_id="mod_123")` is called
- **THEN** the L1 cache for `mod_123` SHALL be cleared
- **AND** the L2 cache file `cache/thumbnails/mod_123.jpg` SHALL be deleted

#### Scenario: Invalidate cache works regardless of path parameter
- **WHEN** `invalidate_cache(item_id="mod_123", path=some_source_path)` is called (e.g., from thumbnail deletion flow)
- **THEN** the L2 cache file `cache/thumbnails/mod_123.jpg` SHALL still be deleted
- **AND** the `path` parameter SHALL NOT prevent L2 cache deletion

#### Scenario: Thumbnail regenerates after cache invalidation
- **WHEN** the grid thumbnail is requested after cache invalidation and the first `preview_images` entry has changed
- **THEN** a new thumbnail SHALL be generated from the updated `preview_images[0]`
- **AND** the foldergrid SHALL display the new thumbnail
