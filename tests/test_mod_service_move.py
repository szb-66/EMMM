"""Verify ModService move / create-folder / auto-group operations.

Checks that folder-name encoding (disabled prefix, pin suffix) is preserved
across a move, that the item id is recomputed for the new parent, and that
auto-group creates the folder and moves items into it.
"""

import tempfile
import unittest
from pathlib import Path

from app.models.mod_item_model import FolderItem, ModStatus
from app.services.mod_service import ModService


class ModServiceMoveTests(unittest.TestCase):
    def setUp(self):
        self.service = ModService(None, None, None, Path())

    def _make_folder_item(self, parent: Path, name: str, status=ModStatus.ENABLED, is_pinned=False):
        folder = parent / name
        folder.mkdir(parents=True, exist_ok=True)
        return FolderItem(
            id="test-id",
            actual_name=name.replace("DISABLED ", "").replace("_pin", ""),
            folder_path=folder,
            status=status,
            is_pinned=is_pinned,
        )

    def test_move_preserves_disabled_prefix_and_pin_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            char_a = root / "CharacterA"
            char_b = root / "CharacterB"
            char_a.mkdir()
            char_b.mkdir()

            item = self._make_folder_item(
                char_a, "DISABLED MyMod_pin", status=ModStatus.DISABLED, is_pinned=True
            )
            result = self.service.move_item_to(item, char_b)

            self.assertTrue(result["success"], result.get("error"))
            new_path = char_b / "DISABLED MyMod_pin"
            self.assertTrue(new_path.exists())
            self.assertFalse((char_a / "DISABLED MyMod_pin").exists())
            self.assertEqual(result["data"].status, ModStatus.DISABLED)
            self.assertTrue(result["data"].is_pinned)

    def test_move_recomputes_id_for_new_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            char_a = root / "CharacterA"
            char_b = root / "CharacterB"
            char_a.mkdir()
            char_b.mkdir()

            item = self._make_folder_item(char_a, "MyMod")
            old_id = item.id
            result = self.service.move_item_to(item, char_b)

            self.assertTrue(result["success"])
            self.assertNotEqual(result["data"].id, old_id)

    def test_move_rejects_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            char_a = root / "CharacterA"
            char_b = root / "CharacterB"
            char_a.mkdir()
            char_b.mkdir()
            # Pre-create the target folder to cause a conflict
            (char_b / "MyMod").mkdir()

            item = self._make_folder_item(char_a, "MyMod")
            result = self.service.move_item_to(item, char_b)

            self.assertFalse(result["success"])
            self.assertIn("already exists", result["error"])

    def test_create_empty_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.service.create_empty_folder(root, "NewFolder")
            self.assertTrue(result["success"])
            self.assertTrue((root / "NewFolder").exists())

    def test_create_empty_folder_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Existing").mkdir()
            result = self.service.create_empty_folder(root, "Existing")
            self.assertFalse(result["success"])

    def test_auto_group_moves_items_into_new_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item_a = self._make_folder_item(root, "ModA")
            item_b = self._make_folder_item(root, "ModB")

            result = self.service.auto_group_items([item_a, item_b], root, "Group1")
            self.assertTrue(result["success"], result.get("error"))
            self.assertTrue((root / "Group1" / "ModA").exists())
            self.assertTrue((root / "Group1" / "ModB").exists())
            self.assertFalse((root / "ModA").exists())
            self.assertFalse((root / "ModB").exists())


if __name__ == "__main__":
    unittest.main()
