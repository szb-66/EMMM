# app/viewmodels/mod_list_vm/_filter_mixin.py
"""Filtering, searching, and widget-dict factory.

Extracted from the original monolithic `mod_list_vm.py` per ADR 0001.
The Mixin must NOT define `__init__` or any `pyqtSignal` — those stay
on the host `ModListViewModel` because pyqtSignal is a Qt descriptor that
must live on a `QObject` subclass.
"""
import dataclasses
from pathlib import Path

from PyQt6.QtCore import QObject  # noqa: F401 — kept to mirror original header

from app.models.mod_item_model import (
    ModStatus,
    ModType,
    BaseModItem,
    ObjectItem,
    CharacterObjectItem,
    GenericObjectItem,
    FolderItem,
)
from app.utils.async_utils import debounce
from app.utils.logger_utils import logger
from app.core.constants import (
    DEBOUNCE_DELAY_MS,
    CONTEXT_OBJECTLIST,
    CONTEXT_FOLDERGRID,
)


class _FilterMixin:
    # --- Filtering, searching, and dict factory ---
    def set_filters(self, filters: dict):
        """
        Flow 5.1: Sets the active detail filters (e.g., rarity, element)
        and triggers a view update.
        """
        logger.info(f"Applying detailed filters: {filters}")
        self.active_filters = filters
        self.apply_filters_and_search()

    def clear_filters(self):
        """
        Clears all active detail filters and triggers a view update.
        """
        if not self.active_filters:
            return

        logger.info("Clearing all detailed filters.")
        self.active_filters = {}
        self.apply_filters_and_search()

    @debounce(DEBOUNCE_DELAY_MS)
    def on_search_query_changed(self, query: str):
        """
        Flow 5.1: Handles live text changes from the search bar with a debounce delay.
        """
        # Sanitize the input query
        sanitized_query = query.lower().strip()

        # Only trigger a refresh if the query has actually changed
        if self.search_query == sanitized_query:
            return

        logger.info(f"Search query changed to: '{sanitized_query}'")
        self.search_query = sanitized_query
        self.apply_filters_and_search()


    # ---Single Item Actions ---

    def _create_dict_from_item(self, item: BaseModItem) -> dict:
        """A helper function to convert any BaseModItem object to a dict for the view."""
        # 1. Start with attributes common to all items

        data = {
            "id": item.id,
            "actual_name": item.actual_name,
            "is_enabled": (item.status == ModStatus.ENABLED),
            "is_pinned": item.is_pinned,
            "is_skeleton": item.is_skeleton,
            "folder_path": item.folder_path,
        }
        # 2. Add attributes specific to the item type

        if isinstance(item, ObjectItem):
            if isinstance(item, CharacterObjectItem):
                data.update(
                    {
                        "thumbnail_path": item.thumbnail_path,
                        "object_type": item.object_type,
                        "tags": item.tags,
                        "gender": item.gender,
                        "rarity": item.rarity,
                        "element": item.element,
                    }
                )
            elif isinstance(item, GenericObjectItem):
                data.update(
                    {
                        "thumbnail_path": item.thumbnail_path,
                        "object_type": item.object_type,
                        "tags": item.tags,
                    }
                )
        elif isinstance(item, FolderItem):
            data.update(
                {
                    "author": item.author,
                    "description": item.description,
                    "tags": item.tags,
                    "preview_images": item.preview_images,
                    "is_navigable": item.is_navigable,
                    "is_safe": item.is_safe,
                }
            )
        return data

    # ---Private/Internal Logic ---

    def apply_filters_and_search(self, item_id_to_select: str = None):
        """
        Filters and sorts the master list based on all active criteria,
        then emits the result for the view to render.
        """
        source_list = self.master_list

        # STAGE 1: Apply main category filter (Character vs Other) if in objectlist context
        if self.context == CONTEXT_OBJECTLIST:
            if self.active_category_filter == ModType.CHARACTER:
                filtered_items = [item for item in source_list if isinstance(item, CharacterObjectItem)]
            else:
                filtered_items = [item for item in source_list if isinstance(item, GenericObjectItem)]
        else:
            filtered_items = source_list

        # STAGE 2: Apply detailed filters from self.active_filters
        if self.active_filters:
                items_after_detail_filter = []
                for item in filtered_items:
                    match = True
                    for key, value in self.active_filters.items():
                        item_value = getattr(item, key, None)

                        # Add logging to see the comparison
                        logger.debug(f"Filtering '{item.actual_name}': Attr '{key}' (Value: {item_value}) vs Filter (Value: {value})")

                        if key == 'tags' and isinstance(value, list):
                            # Handle multi-select for tags
                            if not isinstance(item_value, list) or not set(value).issubset(set(item_value)):
                                match = False
                                break
                        else:
                            # Handle single-select for other fields
                            if item_value != value:
                                match = False
                                break
                    if match:
                        items_after_detail_filter.append(item)
                filtered_items = items_after_detail_filter


        # STAGE 3: Sort the final list
        scored_results = []
        if not self.search_query:
            # If search is empty, assign a neutral score to all items
            scored_results = [(item, 99) for item in filtered_items]
        else:
            # If search is active, score each item based on relevance
            for item in filtered_items:
                score = 99  # Default non-match score

                # Context-aware scoring
                if self.context == CONTEXT_OBJECTLIST:
                    if self.search_query in item.actual_name.lower():
                        score = 1
                    elif item.tags and any(self.search_query in tag.lower() for tag in item.tags):
                        score = 2
                    elif isinstance(item, CharacterObjectItem):
                        if (item.element and self.search_query in item.element.lower()) or \
                            (item.weapon and self.search_query in item.weapon.lower()):
                            score = 3

                elif self.context == CONTEXT_FOLDERGRID:
                    if self.search_query in item.actual_name.lower():
                        score = 1
                    elif item.tags and any(self.search_query in tag.lower() for tag in item.tags):
                        score = 2
                    elif item.author and self.search_query in item.author.lower():
                        score = 3
                    elif item.description and self.search_query in item.description.lower():
                        score = 4

                # Only include items that have a match (score < 99)
                if score < 99:
                    scored_results.append((item, score))

        # --- STAGE 4: Sort the final list ---
        # Sort by: 1. Score (relevance), 2. Pinned, 3. Name
        # ponytail: status removed from sort key — toggling enable/disable
        # no longer relocates the mod within the grid. actual_name is stable
        # because the DISABLED prefix is stripped by _parse_folder_name.
        sorted_results = sorted(
            scored_results,
            key=lambda x: (x[1], not x[0].is_pinned, x[0].actual_name.lower())
        )

        # Extract only the item objects from the (item, score) tuples
        self.displayed_items = [item for item, score in sorted_results]

        # --- STAGE 5: Check for empty results and emit CONTEXT-AWARE state ---
        if not self.displayed_items:
            # This block is now context-aware
            if not self.master_list:
                # Case 1: The folder itself is truly empty.
                if self.context == CONTEXT_OBJECTLIST:
                    title = "No Objects Found"
                    subtitle = "This game's mods folder seems to be empty.\nCreate a new object to get started."
                else: # CONTEXT_FOLDERGRID
                    title = "Folder is Empty"
                    subtitle = "Drag and drop a .zip file or folder here to add a new mod."
                self.empty_state_changed.emit(title, subtitle)

            elif self.search_query or self.active_filters:
                # Case 2: A search/filter was applied and yielded no results (generic message).
                title = "No Matching Results"
                subtitle = "Try adjusting your filter or search terms."
                self.empty_state_changed.emit(title, subtitle)

            else:
                # Case 3: No search/filter, but the base list for the context is empty.
                # This only really applies to the objectlist's category filter.
                if self.context == CONTEXT_OBJECTLIST:
                    category_name = self.active_category_filter.value
                    title = f"No {category_name}s Found"
                    subtitle = f"This category is empty. You can add mods to it."
                    self.empty_state_changed.emit(title, subtitle)
                else:
                    # This case is unlikely for foldergrid but provides a fallback.
                    title = "Folder is Empty"
                    subtitle = "This folder contains no mods."
                    self.empty_state_changed.emit(title, subtitle)

        # --- STAGE 6: Emit filter state for the result bar (BARU) ---
        is_filter_active = bool(self.active_filters or self.search_query)
        found_count = len(self.displayed_items)

        # Show bar only if a filter/search is active AND there are results
        show_bar = is_filter_active and found_count > 0
        self.filter_state_changed.emit(show_bar, found_count)

        # --- STAGE 7: Prepare and emit data for the view ---
        view_data = [self._create_dict_from_item(item) for item in self.displayed_items]
        self.items_updated.emit(view_data, item_id_to_select)

    # ---Private Slots for Async Results ---
    def set_category_filter(self, category: ModType):
        """
        Sets the main category filter for the objectlist and re-applies all filters.
        This is the entry point called from the main orchestrator (MainWindowViewModel).
        """
        # Only apply this logic for the objectlist context
        if self.context != "objectlist" or self.active_category_filter == category:
            return

        logger.info(f"Setting category filter to '{category.value}'")
        self.active_category_filter = category

        # In Stage 3, we will add a signal here to rebuild the filter UI
        self._update_available_filters()

        # Trigger a full view update with the new category filter applied
        self.apply_filters_and_search()

    def _update_available_filters(self):
        """
        [REVISED for ALIAS] Generates available filter options and their
        display names (aliases) based on the game's schema.
        """
        if not self.current_game or not self.current_game.game_type:
            self.available_filters_changed.emit({})
            return

        game_type = self.current_game.game_type
        # The new structure for available_options will be:
        # { 'internal_key': ('DisplayName', [option1, option2]), ... }
        available_options = {}

        if self.context == CONTEXT_OBJECTLIST:
            schema = self.database_service.get_schema_for_game(game_type)
            if not schema:
                self.available_filters_changed.emit({})
                return

            logger.info(f"Generating aliased filter options for 'objectlist' (Game: {game_type}).")

            if self.active_category_filter == ModType.CHARACTER:
                # Define which keys from the schema we want to create filters for
                filter_keys = ["rarity", "element", "gender", "weapon_types"]
                for key in filter_keys:
                    options = schema.get(key, [])
                    if options:
                        # Get the alias for the key, e.g., 'element' -> 'Combat Type'
                        display_name = self.database_service.get_alias_for_game(game_type, key)
                        available_options[key] = (display_name, options)
            else: # For 'Other' categories
                # You can add similar alias logic for subtypes if needed
                all_subtypes = set(i.subtype for i in self.master_list if isinstance(i, GenericObjectItem) and i.subtype)
                if all_subtypes:
                    display_name = self.database_service.get_alias_for_game(game_type, "subtype", fallback="Subtype")
                    available_options['subtype'] = (display_name, sorted(list(all_subtypes)))

        elif self.context == CONTEXT_FOLDERGRID:
            # (Logika untuk foldergrid tetap sama karena tidak menggunakan alias dari schema)
            all_authors = set(i.author for i in self.master_list if isinstance(i, FolderItem) and i.author)
            all_tags = set()
            for item in self.master_list:
                if isinstance(item, FolderItem) and item.tags:
                    all_tags.update(item.tags)
            if all_authors:
                available_options['author'] = ("Author", sorted(list(all_authors)))
            if all_tags:
                available_options['tags'] = ("Tags", sorted(list(all_tags)))

        self.available_filters_changed.emit(available_options)

    def clear_all_filters_and_search(self):
        """Clears all active filters and the search query."""
        should_update = bool(self.active_filters or self.search_query)

        self.active_filters = {}
        self.search_query = ""

        # If there was something to clear, trigger a UI update
        if should_update:
            logger.info("Clearing all filters and search.")
            # Also notify the view to clear the search bar text
            self.clear_search_text.emit()
            self.apply_filters_and_search()
