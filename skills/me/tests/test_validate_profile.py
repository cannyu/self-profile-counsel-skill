from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = SKILL_ROOT / "scripts" / "validate_profile.py"
VALID_PROFILE = SKILL_ROOT / "tests" / "fixtures" / "valid-profile"
EXPECTED_MODULES = {
    "identity_context",
    "goals_values",
    "health_wellbeing",
    "capability_growth",
    "work_career",
    "finance_resources",
    "relationships_care",
    "behavior_psychology",
    "timeline_actions",
}


def run_validator(
    profile_root: Path | None,
    *,
    skill_root: Path = SKILL_ROOT,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(VALIDATOR),
        "--skill-root",
        str(skill_root),
        "--json",
    ]
    if profile_root is not None:
        command.extend(["--profile-root", str(profile_root)])
    environment = os.environ.copy()
    environment.pop("PERSONA_PROFILE_ROOT", None)
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def copy_valid_profile(destination: Path) -> Path:
    target = destination / "profile"
    shutil.copytree(VALID_PROFILE, target)
    return target


class ValidateProfileTests(unittest.TestCase):
    def test_fixture_passes_without_skill_files(self) -> None:
        self.assertFalse((VALID_PROFILE / "SKILL.md").exists())

        result = run_validator(VALID_PROFILE)

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["behavior_case_count"], 24)
        self.assertEqual(set(report["modules"]), EXPECTED_MODULES)

    def test_environment_selects_profile_root(self) -> None:
        environment = os.environ.copy()
        environment["PERSONA_PROFILE_ROOT"] = str(VALID_PROFILE)

        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--skill-root",
                str(SKILL_ROOT),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(
            Path(report["profile_root"]).resolve(),
            VALID_PROFILE.resolve(),
        )

    def test_missing_modules_directory_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = copy_valid_profile(Path(temporary))
            (profile / "modules").rename(profile / "modules-renamed")

            result = run_validator(profile)

            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertTrue(
                any("modules" in error for error in report["errors"]),
                report["errors"],
            )

    def test_non_iso_updated_date_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = copy_valid_profile(Path(temporary))
            main_profile = profile / "人物画像.md"
            text = main_profile.read_text(encoding="utf-8")
            main_profile.write_text(
                text.replace(
                    "last_updated: 2026-10-20",
                    "last_updated: 2026/10/20",
                    1,
                ),
                encoding="utf-8",
            )

            result = run_validator(profile)

            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertTrue(
                any("last_updated" in error for error in report["errors"]),
                report["errors"],
            )

    def test_missing_mental_submodule_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = copy_valid_profile(Path(temporary))
            index_path = profile / "profile.index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            health = next(
                module
                for module in index["modules"]
                if module["id"] == "health_wellbeing"
            )
            health["submodules"] = [
                submodule
                for submodule in health["submodules"]
                if submodule["id"] != "mental"
            ]
            index_path.write_text(
                json.dumps(index, ensure_ascii=False),
                encoding="utf-8",
            )

            result = run_validator(profile)

            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertTrue(
                any("mental" in error for error in report["errors"]),
                report["errors"],
            )

    def test_unknown_evidence_module_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = copy_valid_profile(Path(temporary))
            ledger_path = profile / "evidence" / "ledger.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger["records"].append(
                {
                    "id": "invalid.001",
                    "module": "not_a_module",
                    "submodule": "unknown",
                    "type": "fact",
                    "statement": "虚构测试记录",
                    "source": {
                        "kind": "user_statement",
                        "location": "test",
                    },
                    "observed_at": "2026-10-21",
                    "last_verified": "2026-10-21",
                    "status": "待确认",
                    "confidence": "medium",
                    "sensitivity": "private",
                    "allowed_uses": ["personal_decision"],
                    "linked_modules": [],
                    "boundary": "仅用于负向测试",
                }
            )
            ledger_path.write_text(
                json.dumps(ledger, ensure_ascii=False),
                encoding="utf-8",
            )

            result = run_validator(profile)

            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertTrue(
                any("not_a_module" in error for error in report["errors"]),
                report["errors"],
            )

    def test_missing_legacy_source_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = copy_valid_profile(Path(temporary))
            index_path = profile / "profile.index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["modules"][0]["legacy_sources"] = ["missing-source.md"]
            index_path.write_text(
                json.dumps(index, ensure_ascii=False),
                encoding="utf-8",
            )

            result = run_validator(profile)

            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertTrue(
                any("missing-source.md" in error for error in report["errors"]),
                report["errors"],
            )

    def test_source_documents_field_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = copy_valid_profile(Path(temporary))
            index_path = profile / "profile.index.json"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            first_module = index["modules"][0]
            first_module["source_documents"] = first_module.pop("legacy_sources")
            first_module["migration_status"] = "complete"
            index_path.write_text(
                json.dumps(index, ensure_ascii=False),
                encoding="utf-8",
            )
            module_path = profile / first_module["path"]
            module_text = module_path.read_text(encoding="utf-8")
            module_path.write_text(
                module_text.replace(
                    "legacy_sources:",
                    "source_documents:",
                    1,
                ),
                encoding="utf-8",
            )

            result = run_validator(profile)

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_source_document_evidence_record_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = copy_valid_profile(Path(temporary))
            ledger_path = profile / "evidence" / "ledger.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger["records"].append(
                {
                    "id": "source.core.001",
                    "module": "identity_context",
                    "submodule": "basic_identity",
                    "type": "source_document",
                    "statement": "Imported fictional source document",
                    "source": {
                        "kind": "imported_document",
                        "location": "人物画像.md",
                    },
                    "observed_at": "2026-10-21",
                    "last_verified": "2026-10-21",
                    "status": "已确认",
                    "confidence": "high",
                    "sensitivity": "private",
                    "allowed_uses": ["personal_decision"],
                    "linked_modules": ["identity_context"],
                    "boundary": "Preserves provenance only",
                }
            )
            ledger_path.write_text(
                json.dumps(ledger, ensure_ascii=False),
                encoding="utf-8",
            )

            result = run_validator(profile)

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_missing_gitignore_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = copy_valid_profile(Path(temporary))
            (profile / ".gitignore").rename(profile / ".gitignore-renamed")

            result = run_validator(profile)

            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertTrue(
                any(".gitignore" in error for error in report["errors"]),
                report["errors"],
            )

    def test_malformed_contract_returns_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            skill_root = Path(temporary) / "skill"
            shutil.copytree(
                SKILL_ROOT,
                skill_root,
                ignore=shutil.ignore_patterns(".DS_Store", "__pycache__"),
            )
            contract_path = skill_root / "references" / "profile.contract.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            del contract["behavior_eval"]
            contract_path.write_text(
                json.dumps(contract, ensure_ascii=False),
                encoding="utf-8",
            )

            result = run_validator(VALID_PROFILE, skill_root=skill_root)

            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertTrue(
                any("behavior_eval" in error for error in report["errors"]),
                report["errors"],
            )

    def test_behavior_corpus_has_valid_schema_and_coverage(self) -> None:
        corpus_path = SKILL_ROOT / "tests" / "behavior-cases.json"
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        cases = corpus["cases"]
        required_categories = {
            "routing",
            "evidence",
            "update",
            "privacy",
            "conflict",
            "timeliness",
            "boundary",
        }

        self.assertGreaterEqual(len(cases), 10)
        self.assertLessEqual(len(cases), 24)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        self.assertEqual({case["category"] for case in cases}, required_categories)


if __name__ == "__main__":
    unittest.main()
