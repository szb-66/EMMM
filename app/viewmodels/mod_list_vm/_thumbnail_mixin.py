# app/viewmodels/mod_list_vm/_thumbnail_mixin.py
"""Thumbnail retrieval + thumbnail-generated callback.

Extracted from the original monolithic ``mod_list_vm.py`` per ADR 0001.
The Mixin must NOT define ``__init__`` or any ``pyqtSignal``.
"""
import dataclasses
from pathlib import Path

from PyQt6.QtGui import QPixmap

from app.models.mod_item_model import ObjectItem
from app.utils.logger_utils import logger


class _ThumbnailMixin:
    # --- Thumbnail retrieval and async-generation callback ---

    def get_thumbnail(
        self, item_id: str, source_path: Path | None, default_type: str
    ) -> QPixmap:
        """
        Flow 2.4, Step 2: A wrapper method that delegates the thumbnail request to the service.
        This decouples the View from having to know about the ThumbnailService directly.
        """
        return self.thumbnail_service.get_thumbnail(
            item_id=item_id, source_path=source_path, default_type=default_type
        )

    def get_initial_name(self, name: str):
        """
        Generates an initial from the name for avatar display.
        """
        return self.system_utils.get_initial_name(name, length=2)

    def _on_thumbnail_generated(self, item_id: str, cache_path: Path):
        """
        Receives a signal from ThumbnailService when a new thumbnail is ready on disk.
        Updates the internal item model and triggers a targeted UI refresh.
        """

        try:
            # 1. Find the appropriate item in Master_list

            item_to_update = next(
                item for item in self.master_list if item.id == item_id
            )
            if not item_to_update:
                logger.warning(
                    f"Item '{item_id}' no longer in list when its thumbnail was ready."
                )
                return

            updated_item = item_to_update

            # ---Revised Logic: Check Item Type Before Updating ---
            # 2. Only update the model if it is Objectitem

            if isinstance(item_to_update, ObjectItem):
                # Update the thumbnail_path to point to the new cache file.
                # This helps in case of a full refresh, it can load from cache directly.

                updated_item = dataclasses.replace(
                    item_to_update, thumbnail_path=cache_path
                )

                # Replace the old item with the new one in the internal state

                master_idx = self.master_list.index(item_to_update)
                self.master_list[master_idx] = updated_item

                if item_to_update in self.displayed_items:
                    display_idx = self.displayed_items.index(item_to_update)
                    self.displayed_items[display_idx] = updated_item

            # For FolderItem, we don't need to change the model. The fact that the
            # thumbnail exists in the cache is enough. We just need to trigger a UI update.

            # 4. Use the existing 'item_needs_update' signal to trigger UI refresh
            #    targeted to just one widget.

            view_data = self._create_dict_from_item(updated_item)
            self.item_needs_update.emit(view_data)

        except (StopIteration, ValueError):
            logger.warning(
                f"Item '{item_id}' not found in list when its thumbnail was ready. It may have been unloaded."
            )

