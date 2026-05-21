import tempfile
import unittest
from pathlib import Path

from app.models.mod_item_model import FolderItem, ModStatus, ObjectItem
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
            self.assertIn(
                "persistent_state_snapshot",
                (disabled_item.folder_path / "info.json").read_text(encoding="utf-8"),
            )
            saved = (disabled_item.folder_path / "merged.ini").read_text(
                encoding="utf-8"
            )
            self.assertIn("global persist $swapvar = 5", saved)
            self.assertIn("$swapvar = 0,1,2,3,4,5", saved)
            self.assertTrue(
                (disabled_item.folder_path / "merged.ini.backup").exists()
            )

            user_config.write_text("[Constants]\n", encoding="utf-8")

            enabled_result = service.toggle_status(disabled_item, ModStatus.ENABLED)
            self.assertTrue(enabled_result["success"])
            self.assertIn(
                r"$\mods\character\some mod\merged.ini\swapvar = 5",
                user_config.read_text(encoding="utf-8"),
            )

    def test_toggle_disable_syncs_namespace_runtime_state_to_source_ini(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod_dir = root / "Mods" / "Character" / "Some Mod"
            mod_dir.mkdir(parents=True)
            ini_path = mod_dir / "merged.ini"
            ini_path.write_text(
                "\n".join(
                    [
                        "namespace = some_namespace",
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
            (mod_dir / "info.json").write_text("{}", encoding="utf-8")
            user_config = root / "d3dx_user.ini"
            user_config.write_text(
                "\n".join(
                    [
                        "[Constants]",
                        r"$\some_namespace\swapvar = 2",
                        r"$\unrelated_namespace\swapvar = 9",
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
            saved = (disabled_item.folder_path / "merged.ini").read_text(
                encoding="utf-8"
            )
            self.assertIn("global persist $swapvar = 2", saved)
            self.assertIn("$swapvar = 0,1,2", saved)
            self.assertTrue(
                (disabled_item.folder_path / "merged.ini.backup").exists()
            )
            metadata = (disabled_item.folder_path / "info.json").read_text(
                encoding="utf-8"
            )
            self.assertIn(r"$\\some_namespace\\swapvar", metadata)
            self.assertNotIn("unrelated_namespace", metadata)

    def test_toggle_disable_snapshots_object_item_state_to_properties_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            object_dir = root / "Mods" / "Character" / "Some Object"
            object_dir.mkdir(parents=True)
            (object_dir / "merged.ini").write_text(
                "\n".join(
                    [
                        "[Constants]",
                        "global persist $swapvar = 0",
                        "",
                        "[KeySwap]",
                        "key = n",
                        "type = cycle",
                        "$swapvar = 0,1",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (object_dir / "properties.json").write_text("{}", encoding="utf-8")
            (root / "d3dx_user.ini").write_text(
                "\n".join(
                    [
                        "[Constants]",
                        r"$\mods\character\some object\merged.ini\swapvar = 1",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            service = ModService(None, None, None, root)
            item = ObjectItem(
                id="1",
                actual_name="Some Object",
                folder_path=object_dir,
                status=ModStatus.ENABLED,
                is_pinned=False,
            )

            disabled_result = service.toggle_status(item, ModStatus.DISABLED)

            self.assertTrue(disabled_result["success"])
            disabled_item = disabled_result["data"]
            metadata = (
                disabled_item.folder_path / "properties.json"
            ).read_text(encoding="utf-8")
            self.assertIn("persistent_state_snapshot", metadata)
            self.assertIn(
                r"$\\mods\\character\\some object\\merged.ini\\swapvar",
                metadata,
            )


    def test_cross_file_persist_detected_in_shared_vars_phase(self):
        """global persist in file A, [Key] section in file B → detected."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod_dir = root / "Mods" / "Character" / "MultiFileMod"
            mod_dir.mkdir(parents=True)

            # File A: global persist declaration only (no [Key] sections)
            (mod_dir / "decls.ini").write_text(
                "\n".join(
                    [
                        "[Constants]",
                        "global persist $swapvar = 0",
                        "global persist $color = 1",
                    ]
                ),
                encoding="utf-8",
            )

            # File B: [Key] section referencing $swapvar (no global persist here)
            (mod_dir / "keys.ini").write_text(
                "\n".join(
                    [
                        "[KeyToggle]",
                        "key = n",
                        "type = cycle",
                        "$swapvar = 0,1,2",
                    ]
                ),
                encoding="utf-8",
            )

            (root / "d3dx_user.ini").write_text(
                "\n".join(
                    [
                        "[Constants]",
                        r"$\mods\character\multifilemod\keys.ini\swapvar = 2",
                        r"$\mods\character\multifilemod\decls.ini\color = 0",
                    ]
                ),
                encoding="utf-8",
            )

            service = IniKeyParsingService()
            result = service.get_runtime_persistent_assignments(mod_dir, root)

            self.assertEqual(len(result), 2)
            assign = next(a for a in result if a.variable == "$swapvar")
            self.assertEqual(assign.current_value, "2")
            self.assertIn("swapvar", assign.persist_key.lower())

            color = next(a for a in result if a.variable == "$color")
            self.assertEqual(color.current_value, "0")

    def test_orphan_persist_var_only_in_commandlist_is_detected(self):
        """global persist var only modified via CommandList → detected."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod_dir = root / "Mods" / "Character" / "CmdListMod"
            mod_dir.mkdir(parents=True)

            ini_path = mod_dir / "mod.ini"
            ini_path.write_text(
                "\n".join(
                    [
                        "[Constants]",
                        "global persist $corruption = 0",
                        "",
                        "[KeyToggle]",
                        "key = n",
                        "type = cycle",
                        "$swapvar = 0,1",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "d3dx_user.ini").write_text(
                "\n".join(
                    [
                        "[Constants]",
                        r"$\mods\character\cmdlistmod\mod.ini\corruption = 50",
                        r"$\mods\character\cmdlistmod\mod.ini\swapvar = 1",
                    ]
                ),
                encoding="utf-8",
            )

            service = IniKeyParsingService()
            result = service.get_runtime_persistent_assignments(mod_dir, root)

            corruption = next(
                (a for a in result if a.variable == "$corruption"), None
            )
            self.assertIsNotNone(corruption)
            self.assertEqual(corruption.current_value, "50")
            self.assertIn("corruption", corruption.persist_key.lower())

    def test_orphan_persist_var_without_runtime_key_is_skipped(self):
        """orphan persist var not in d3dx_user.ini → not returned."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod_dir = root / "Mods" / "Character" / "OrphanSkipped"
            mod_dir.mkdir(parents=True)

            (mod_dir / "mod.ini").write_text(
                "\n".join(
                    [
                        "[Constants]",
                        "global persist $orphan = 99",
                        "",
                        "[KeyToggle]",
                        "key = n",
                        "$color = 0,1",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "d3dx_user.ini").write_text(
                "\n".join(
                    [
                        "[Constants]",
                        r"$\mods\character\orphanskipped\mod.ini\color = 1",
                        # $orphan has NO runtime entry
                    ]
                ),
                encoding="utf-8",
            )

            service = IniKeyParsingService()
            result = service.get_runtime_persistent_assignments(mod_dir, root)

            # $color is not persistent, $orphan has no runtime key — result should be empty
            self.assertEqual(len(result), 0)

    def test_parse_single_ini_without_folder_vars_is_backward_compatible(self):
        """Calling _parse_single_ini without folder_persistent_vars → unchanged."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod_dir = root / "Mods" / "Character" / "CompatTest"
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
                    ]
                ),
                encoding="utf-8",
            )

            service = IniKeyParsingService()
            bindings = service._parse_single_ini(
                ini_path, root, {},
                # no folder_persistent_vars (= None) — default behavior
            )

            self.assertEqual(len(bindings), 1)
            assignment = bindings[0].assignments[0]
            self.assertTrue(assignment.is_persistent)
            self.assertEqual(assignment.variable, "$swapvar")

    def test_cross_file_namespace_persist_is_detected(self):
        """namespace in file A, [Key] section in file B, runtime via namespace key."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mod_dir = root / "Mods" / "Character" / "NsCrossFile"
            mod_dir.mkdir(parents=True)

            (mod_dir / "decls.ini").write_text(
                "\n".join(
                    [
                        "namespace = TestNs",
                        "global persist $body = 1",
                    ]
                ),
                encoding="utf-8",
            )
            (mod_dir / "keys.ini").write_text(
                "\n".join(
                    [
                        "namespace = TestNs",
                        "[KeyBody]",
                        "key = b",
                        "type = cycle",
                        "$body = 0,1",
                    ]
                ),
                encoding="utf-8",
            )
            (root / "d3dx_user.ini").write_text(
                "\n".join(
                    [
                        "[Constants]",
                        r"$\testns\body = 0",
                    ]
                ),
                encoding="utf-8",
            )

            service = IniKeyParsingService()
            result = service.get_runtime_persistent_assignments(mod_dir, root)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].variable, "$body")
            self.assertEqual(result[0].current_value, "0")
            self.assertIn(r"$\testns\body", result[0].persist_key)


if __name__ == "__main__":
    unittest.main()
