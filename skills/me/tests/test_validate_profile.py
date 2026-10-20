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
        self.assertEqual(report["behavior_case_count"], 16)

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

    def test_missing_domain_directory_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            profile = copy_valid_profile(Path(temporary))
            (profile / "专项档案").rename(profile / "专项档案-renamed")

            result = run_validator(profile)

            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertTrue(
                any("专项档案" in error for error in report["errors"]),
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
        self.assertLessEqual(len(cases), 20)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        self.assertEqual({case["category"] for case in cases}, required_categories)


if __name__ == "__main__":
    unittest.main()
