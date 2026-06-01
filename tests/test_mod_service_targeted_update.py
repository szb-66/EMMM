"""Verify that ModService update operations return complete item models
so callers can emit targeted UI updates instead of triggering full reloads.
"""

import tempfile
import unittest
from pathlib import Path

from app.models.mod_item_model import (
    FolderItem,
    ModStatus,
    ObjectItem,
    ModType,
    CharacterObjectItem,
    GenericObjectItem,
)
from app.services.mod_service import ModService


class ModServiceTargetedUpdateTests(unittest.TestCase):
    """Integration tests for update operations returning full item models."""

    def setUp(self):
        # Most tests don't need real DatabaseService / ImageUtils / SystemUtils
        # for the code paths we exercise, so we pass None for those
        # dependencies.  ModService uses DatabaseService for reconciliation
        # paths only; the update paths don't touch it.
        self.service = ModService(None, None, None, Path())

    # ------------------------------------------------------------------
    # update_object — returns updated item model on success
    # ------------------------------------------------------------------
    def test_update_object_returns_complete_item_model_on_success(self):
        """After a successful update_object call, the result dict MUST
        include a ``data`` key populated with the updated ObjectItem model
        so the ViewModel can emit a targeted ``item_needs_update`` signal."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            object_dir = root / "Some Object"
            object_dir.mkdir(parents=True)
            (object_dir / "properties.json").write_text(
                '{"object_type": "Character", "rarity": 4}', encoding="utf-8"
            )

            item = CharacterObjectItem(
                id="obj-1",
                actual_name="Some Object",
                folder_path=object_dir,
                status=ModStatus.ENABLED,
                is_pinned=False,
                object_type=ModType.CHARACTER,
                rarity=4,
            )

            result = self.service.update_object(item, {"rarity": 5})

            self.assertTrue(result["success"], msg=f"update failed: {result.get('error')}")
            self.assertEqual(result["item_id"], "obj-1")

            # The key assertion: data must contain the updated model.
            self.assertIn("data", result, "Result must include updated item model under 'data'")
            updated = result["data"]
            self.assertIsInstance(updated, ObjectItem)
            self.assertEqual(updated.rarity, 5)
            self.assertEqual(updated.actual_name, "Some Object")

    # ------------------------------------------------------------------
    # update_object — handles rename
    # ------------------------------------------------------------------
    def test_update_object_rename_returns_new_path_and_name(self):
        """Renaming an object via update_object must return the new
        folder_path and actual_name in the updated model."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            object_dir = root / "Old Name"
            object_dir.mkdir(parents=True)

            item = GenericObjectItem(
                id="obj-2",
                actual_name="Old Name",
                folder_path=object_dir,
                status=ModStatus.ENABLED,
                is_pinned=False,
                object_type=ModType.OTHER,
            )

            result = self.service.update_object(item, {"name": "New Name", "subtype": "Weapon"})

            self.assertTrue(result["success"], msg=f"update failed: {result.get('error')}")
            updated = result["data"]
            self.assertEqual(updated.actual_name, "New Name")
            self.assertTrue(updated.folder_path.name.startswith("New Name"),
                            f"Folder should be renamed, got: {updated.folder_path.name}")
            self.assertTrue(updated.folder_path.is_dir(),
                            f"Renamed folder must exist: {updated.folder_path}")

    # ------------------------------------------------------------------
    # update_object — failure case
    # ------------------------------------------------------------------
    def test_update_object_failure_does_not_include_data(self):
        """On failure, the result dict should NOT include a 'data' key
        (callers guard on result['success'] before accessing it)."""
        # Use a non-existent folder to force failure
        item = GenericObjectItem(
            id="bad-1",
            actual_name="Ghost",
            folder_path=Path("/no/such/path/ghost"),
            status=ModStatus.ENABLED,
            is_pinned=False,
            object_type=ModType.OTHER,
        )

        result = self.service.update_object(item, {"name": "Whatever"})

        self.assertFalse(result["success"])
        # data key must be absent, not present-with-None
        self.assertNotIn("data", result)


if __name__ == "__main__":
    unittest.main()
