from __future__ import annotations

import json
import unittest
from pathlib import Path


ME_SKILL = Path(__file__).resolve().parents[1]
ME_PLUGIN = ME_SKILL.parents[1]
PLUGINS_ROOT = ME_PLUGIN.parent


class PluginLayoutTests(unittest.TestCase):
    def test_workspace_marketplace_lists_me_and_asu(self) -> None:
        marketplace_path = PLUGINS_ROOT / ".agents" / "plugins" / "marketplace.json"
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))

        self.assertEqual(marketplace["name"], "workspace-plugins")
        self.assertEqual(
            {plugin["name"] for plugin in marketplace["plugins"]},
            {"asu-skills", "persona-profile-skill"},
        )

    def test_me_plugin_has_expected_manifest(self) -> None:
        manifest = json.loads(
            (ME_PLUGIN / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(manifest["name"], "persona-profile-skill")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertEqual(ME_PLUGIN.name, "persona-profile-skill")
        self.assertIsInstance(manifest["author"], dict)
        self.assertTrue(manifest["author"].get("name"))
        self.assertTrue(manifest["interface"]["longDescription"])
        self.assertTrue(manifest["interface"]["developerName"])

    def test_asu_plugin_preserves_manifest_and_skills(self) -> None:
        asu_plugin = PLUGINS_ROOT / "asu-skills"
        manifest = json.loads(
            (asu_plugin / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(manifest["name"], "asu-skills")
        self.assertTrue((asu_plugin / "skills" / "interview" / "SKILL.md").is_file())

    def test_me_plugin_does_not_contain_profile_data(self) -> None:
        self.assertFalse((ME_PLUGIN / "人物画像.md").exists())
        self.assertFalse((ME_PLUGIN / "专项档案").exists())
        self.assertFalse((ME_PLUGIN / "行动清单.md").exists())

    def test_plugin_has_public_repository_documents(self) -> None:
        self.assertTrue((ME_PLUGIN / "README.md").is_file())
        self.assertTrue((ME_PLUGIN / "LICENSE").is_file())
        self.assertFalse((ME_PLUGIN / "docs").exists())

    def test_skill_has_no_personal_examples_or_home_paths(self) -> None:
        production_files = [
            ME_SKILL / "SKILL.md",
            ME_SKILL / "references" / "profile-contract.md",
            ME_SKILL / "references" / "profile.contract.json",
            ME_SKILL / "scripts" / "validate_profile.py",
        ]
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in production_files
        )

        for forbidden in ("/Users/", "his own life", "他明确"):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
