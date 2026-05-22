## ADDED Requirements

### Requirement: Preview image gallery is horizontally scrollable
The preview image area SHALL display images in a horizontally scrollable gallery layout. Multiple thumbnails SHALL be visible simultaneously, and the user SHALL scroll horizontally via mouse wheel or scrollbar to browse all images.

#### Scenario: Gallery shows multiple thumbnails
- **WHEN** a mod with 5 preview images is selected
- **THEN** the gallery SHALL show multiple thumbnails at once (not a single flip view)
- **AND** a horizontal scrollbar SHALL appear if not all thumbnails fit in the visible area

#### Scenario: Mouse wheel scrolls gallery
- **WHEN** the user scrolls the mouse wheel over the gallery
- **THEN** the gallery SHALL scroll horizontally to reveal adjacent images

### Requirement: Gallery width adapts to panel resize
The gallery SHALL fill the available panel width. When the user resizes the detail panel, the gallery width and thumbnail sizes SHALL update accordingly.

#### Scenario: Panel resize updates gallery width
- **WHEN** the user drags the detail panel wider from 400px to 700px
- **THEN** the gallery width SHALL increase to fill the new panel width
- **AND** thumbnail sizes SHALL recalculate based on the available width

#### Scenario: Thumbnail width formula
- **WHEN** the available gallery width is 600px
- **THEN** each thumbnail SHALL be sized to fill approximately 1/3 to 1/4 of the available width
- **AND** the thumbnail height SHALL maintain the image's aspect ratio

### Requirement: Gallery images are clickable for deletion
The gallery SHALL maintain the current image selection concept — clicking a thumbnail selects it, and the remove button deletes the selected image.

#### Scenario: Click selects thumbnail
- **WHEN** the user clicks on a thumbnail in the gallery
- **THEN** that thumbnail SHALL be visually highlighted as selected
- **AND** the index label SHALL update to show "X / Y"

#### Scenario: Remove deletes selected image
- **WHEN** the user clicks the remove button while a thumbnail is selected
- **THEN** the selected image SHALL be removed after confirmation
- **AND** the gallery SHALL refresh to show the remaining images

### Requirement: User can set current image as cover
The gallery SHALL provide a "Set as Cover" button that promotes the selected/current image to the first position in `preview_images`, making it the mod's cover thumbnail in the foldergrid.

#### Scenario: Set as cover reorders images
- **WHEN** the user clicks the "Set as Cover" button on the third image
- **THEN** that image SHALL move to index 0 in `preview_images`
- **AND** the foldergrid thumbnail SHALL update to show the new cover image
- **AND** the gallery SHALL refresh to reflect the new order

#### Scenario: Set as cover button visibility
- **WHEN** there are at least 2 preview images
- **THEN** the "Set as Cover" button SHALL be visible
- **WHEN** there is 0 or 1 preview image
- **THEN** the "Set as Cover" button SHALL be hidden
