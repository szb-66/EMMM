import tempfile
import unittest
from pathlib import Path

from app.models.mod_item_model import FolderItem, ModStatus
from app.services.Iniparsing_service import IniKeyParsingService
from app.services.mod_service import ModService
from app.services.persist_utils import read_user_persist_values


class IniPersistenceTests(unittest.TestCase):
    def test_persist_value_comes_from_d3dx_user_with_disabled_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod_dir = root / "Mods" / "Character" / "DISABLED Some Mod"
            mod_dir.mkdir(parents=True)
            ini_path = mod_dir / "merged.ini"
            ini_path.write_text(
                "\n".join(
                    [
                        "[Constants]",
                        "global persist $swapvar = 0",
                        "",
                        "[KeySwap]",
                        "key = n",
                        "type = cycle",
                        "$swapvar = 0,1,2",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "d3dx_user.ini").write_text(
                "\n".join(
                    [
                        "[Constants]",
                        r"$\mods\character\some mod\merged.ini\swapvar = 2",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            service = IniKeyParsingService()
            user_values = read_user_persist_values(root / "d3dx_user.ini")
            bindings = service._parse_single_ini(ini_path, root, user_values)

            assignment = bindings[0].assignments[0]
            self.assertTrue(assignment.is_persistent)
            self.assertEqual(assignment.current_value, "2")
            self.assertEqual(
                assignment.persist_key,
                r"$\mods\character\some mod\merged.ini\swapvar",
            )

    def test_save_updates_persist_default_without_collapsing_cycle_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod_dir = root / "Mods" / "Character" / "Some Mod"
            mod_dir.mkdir(parents=True)
            ini_path = mod_dir / "merged.ini"
            ini_path.write_text(
                "\n".join(
                    [
                        "[Constants]",
                        "global persist $swapvar = 0",
                        "",
                        "[KeySwap]",
                        "key = n",
                        "type = cycle",
                        "$swapvar = 0,1,2",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            service = IniKeyParsingService()
            bindings = service._parse_single_ini(ini_path, root, {})
            bindings[0].assignments[0].current_value = "1"

            result = service.save_ini_changes(bindings)

            self.assertTrue(result["success"])
            saved = ini_path.read_text(encoding="utf-8")
            self.assertIn("global persist $swapvar = 1", saved)
            self.assertIn("$swapvar = 0,1,2", saved)
            self.assertTrue(ini_path.with_suffix(".ini.backup").exists())

    def test_save_updates_xxmi_user_config_for_f10_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod_dir = root / "Mods" / "Character" / "Some Mod"
            mod_dir.mkdir(parents=True)
            ini_path = mod_dir / "merged.ini"
            ini_path.write_text(
                "\n".join(
                    [
                        "[Constants]",
                        "global persist $swapvar = 0",
                        "",
                        "[KeySwap]",
                        "key = n",
                        "type = cycle",
                        "$swapvar = 0,1,2",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "d3dx_user.ini").write_text(
                "\n".join(
                    [
                        "; AUTOMATICALLY GENERATED FILE - DO NOT EDIT",
                        "[Constants]",
                        r"$\mods\character\some mod\merged.ini\swapvar = 0",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            service = IniKeyParsingService()
            bindings = service._parse_single_ini(ini_path, root, {})
            bindings[0].assignments[0].current_value = "2"

            result = service.save_ini_changes(bindings)

            self.assertTrue(result["success"])
            user_config = (root / "d3dx_user.ini").read_text(encoding="utf-8")
            self.assertIn(
                r"$\mods\character\some mod\merged.ini\swapvar = 2",
                user_config,
            )

    def test_toggle_disable_snapshots_state_and_enable_restores_after_f10_wipe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod_dir = root / "Mods" / "Character" / "Some Mod"
            mod_dir.mkdir(parents=True)
            (mod_dir / "merged.ini").write_text(
                "\n".join(
                    [
                        "[Constants]",
                        "global persist $swapvar = 0",
                        "",
                        "[KeySwap]",
                        "key = n",
                        "type = cycle",
                        "$swapvar = 0,1,2,3,4,5",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (mod_dir / "info.json").write_text("{}", encoding="utf-8")
            user_config = root / "d3dx_user.ini"
            user_config.write_text(
                "\n".join(
                    [
                        "[Constants]",
                        r"$\mods\character\some mod\merged.ini\swapvar = 5",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            service = ModService(None, None, None, root)
            item = FolderItem(
                id="1",
                actual_name="Some Mod",
                folder_path=mod_dir,
                status=ModStatus.ENABLED,
                is_pinned=False,
            )

            disabled_result = service.toggle_status(item, ModStatus.DISABLED)
            self.assertTrue(disabled_result["success"])
            disabled_item = disabled_result["data"]
            self.assertIn("persistent_state_snapshot", (disabled_item.folder_path / "info.json").read_text(encoding="utf-8"))

            user_config.write_text("[Constants]\n", encoding="utf-8")

            enabled_result = service.toggle_status(disabled_item, ModStatus.ENABLED)
            self.assertTrue(enabled_result["success"])
            self.assertIn(
                r"$\mods\character\some mod\merged.ini\swapvar = 5",
                user_config.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
