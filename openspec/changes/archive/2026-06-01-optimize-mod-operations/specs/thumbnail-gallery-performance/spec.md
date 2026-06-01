# Thumbnail Gallery Performance

**Responsibility:** Define incremental gallery update behavior, persistent pixmap cache lifecycle, and lazy-loading strategy.

## ADDED Requirements

### Requirement: Gallery operations affect only the target thumbnail
When the user adds, removes, or reorders preview images, the gallery SHALL update only the affected thumbnails rather than rebuilding the entire widget set. Unchanged thumbnails SHALL retain their existing widgets and cached pixmaps.

#### Scenario: Adding one image does not rebuild existing thumbnails
- **WHEN** a mod has 5 preview images displayed in the gallery and the user adds a 6th image
- **THEN** the 5 existing thumbnail widgets SHALL remain intact (not destroyed and recreated)
- **AND** a new thumbnail widget SHALL be inserted at the appropriate position in the gallery
- **AND** the index label SHALL update from "5 / 5" to "6 / 6"

#### Scenario: Removing one image preserves remaining thumbnails
- **WHEN** a mod has 5 preview images displayed and the user removes the 3rd image
- **THEN** only the thumbnail widget at index 2 SHALL be removed
- **AND** the remaining 4 thumbnail widgets SHALL NOT be destroyed or recreated
- **AND** their internal index references SHALL update to reflect the new order

#### Scenario: Reordering images preserves all widgets
- **WHEN** the user sets the last image as cover (moves it to index 0)
- **THEN** no thumbnail widgets SHALL be destroyed or created
- **AND** the gallery SHALL reorder the existing widgets in the layout to reflect the new order

### Requirement: Pixmap cache survives item transitions
The gallery SHALL maintain an in-memory pixmap cache that persists when the user switches between mods. Re-selecting a mod whose images were previously loaded SHALL NOT re-read those images from disk.

#### Scenario: Re-selecting a mod uses cached pixmaps
- **WHEN** the user selects Mod A (5 images loaded into gallery), then selects Mod B, then selects Mod A again
- **THEN** the gallery SHALL display Mod A's 5 images from the in-memory pixmap cache
- **AND** no image files SHALL be read from disk for Mod A's thumbnails

#### Scenario: Cache is cleared when images are deleted from disk
- **WHEN** the user removes a preview image from a mod
- **THEN** that image's entry in the pixmap cache SHALL be invalidated
- **AND** unchanged images SHALL retain their cache entries

### Requirement: Pixmap cache has bounded size
The gallery SHALL limit the pixmap cache to prevent unbounded memory growth. When the cache exceeds the maximum entry count, the least recently used entry SHALL be evicted.

#### Scenario: Cache eviction on overflow
- **WHEN** the pixmap cache contains 200 entries and a new image is loaded
- **THEN** the least recently used entry SHALL be evicted
- **AND** the new image SHALL be added to the cache
