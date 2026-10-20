#!/usr/bin/env python3
"""Validate the local persona-profile skill without third-party dependencies."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
DEFAULT_PROFILE_ROOT = Path.home() / "workspace" / "人物画像"
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)", re.DOTALL)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VERSION_RE = re.compile(r"^v?\d+(?:\.\d+)+$")
REQUIRED_CONTRACT_KEYS = {
    "schema_version",
    "plugin_required_files",
    "profile_required_files",
    "required_directories",
    "profile_frontmatter_required",
    "domain_frontmatter_required",
    "main_required_sections",
    "domain_required_section_groups",
    "readme_required_sections",
    "allowed_evidence_layers",
    "uncertainty_marker",
    "privacy",
    "behavior_eval",
}


@dataclass
class Report:
    skill_root: Path
    profile_root: Path
    errors: list[str] = field(default_factory=list)
    checks: int = 0
    behavior_case_count: int = 0

    def check(self, condition: bool, message: str) -> None:
        self.checks += 1
        if not condition:
            self.errors.append(message)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str | None]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, "缺少 YAML frontmatter"

    data: dict[str, str] = {}
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator or not key.strip():
            return {}, f"无法解析 frontmatter 行：{raw_line!r}"
        stripped = value.strip()
        if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'":
            stripped = stripped[1:-1]
        data[key.strip()] = stripped
    return data, None


def validate_frontmatter(
    report: Report,
    relative_path: str,
    text: str,
    required_fields: list[str],
    required_visibility: str,
) -> None:
    data, error = parse_frontmatter(text)
    if error:
        report.check(False, f"{relative_path}: {error}")
        return
    report.check(True, f"{relative_path}: frontmatter 可解析")

    missing = [field for field in required_fields if not data.get(field)]
    report.check(
        not missing,
        f"{relative_path}: frontmatter 缺少字段 {', '.join(missing)}",
    )

    last_updated = data.get("last_updated", "")
    valid_date = bool(DATE_RE.fullmatch(last_updated))
    if valid_date:
        try:
            date.fromisoformat(last_updated)
        except ValueError:
            valid_date = False
    report.check(
        valid_date,
        f"{relative_path}: last_updated 必须是合法的 YYYY-MM-DD 日期",
    )

    version = data.get("version", "")
    report.check(
        bool(VERSION_RE.fullmatch(version)),
        f"{relative_path}: version 必须是 1.0 或 v2.0 形式",
    )

    report.check(
        required_visibility in data.get("visibility", ""),
        f"{relative_path}: visibility 必须包含“{required_visibility}”",
    )


def validate_required_sections(
    report: Report,
    relative_path: str,
    text: str,
    required_sections: list[str],
) -> None:
    missing = [section for section in required_sections if section not in text]
    report.check(
        not missing,
        f"{relative_path}: 缺少必需章节 {', '.join(missing)}",
    )


def validate_section_groups(
    report: Report,
    relative_path: str,
    text: str,
    groups: list[list[str]],
) -> None:
    missing = [
        " / ".join(group)
        for group in groups
        if not any(section in text for section in group)
    ]
    report.check(
        not missing,
        f"{relative_path}: 缺少必需章节组 {', '.join(missing)}",
    )


def load_contract(skill_root: Path, report: Report) -> dict[str, Any] | None:
    path = skill_root / "references" / "profile.contract.json"
    report.check(path.is_file(), "Skill 缺少 references/profile.contract.json")
    if not path.is_file():
        return None
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        report.check(False, f"references/profile.contract.json 无法读取：{error}")
        return None
    report.check(
        isinstance(contract, dict) and contract.get("schema_version") == SCHEMA_VERSION,
        f"references/profile.contract.json: schema_version 必须为 {SCHEMA_VERSION}",
    )
    if not isinstance(contract, dict):
        return None

    missing = sorted(REQUIRED_CONTRACT_KEYS - set(contract))
    report.check(
        not missing,
        f"references/profile.contract.json: 缺少字段 {', '.join(missing)}",
    )
    list_fields = (
        "plugin_required_files",
        "profile_required_files",
        "required_directories",
        "profile_frontmatter_required",
        "domain_frontmatter_required",
        "main_required_sections",
        "readme_required_sections",
        "allowed_evidence_layers",
    )
    for field_name in list_fields:
        value = contract.get(field_name)
        report.check(
            isinstance(value, list)
            and all(isinstance(item, str) and item.strip() for item in value),
            f"references/profile.contract.json: {field_name} 必须是非空字符串数组",
        )
    privacy = contract.get("privacy")
    report.check(
        isinstance(privacy, dict)
        and isinstance(privacy.get("required_visibility_marker"), str)
        and isinstance(privacy.get("required_gitignore_patterns"), list),
        "references/profile.contract.json: privacy 字段结构无效",
    )
    behavior_eval = contract.get("behavior_eval")
    report.check(
        isinstance(behavior_eval, dict)
        and isinstance(behavior_eval.get("min_cases"), int)
        and isinstance(behavior_eval.get("max_cases"), int)
        and isinstance(behavior_eval.get("required_categories"), list),
        "references/profile.contract.json: behavior_eval 字段结构无效",
    )
    groups = contract.get("domain_required_section_groups")
    report.check(
        isinstance(groups, list)
        and all(
            isinstance(group, list)
            and group
            and all(isinstance(section, str) and section.strip() for section in group)
            for group in groups
        )
        if isinstance(groups, list)
        else False,
        "references/profile.contract.json: domain_required_section_groups 字段结构无效",
    )

    if report.errors:
        return None
    return contract


def validate_behavior_cases(root: Path, contract: dict[str, Any], report: Report) -> None:
    relative = "tests/behavior-cases.json"
    path = root / relative
    if not path.is_file():
        return
    try:
        corpus = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        report.check(False, f"{relative}: 无法解析 JSON：{error}")
        return

    cases = corpus.get("cases") if isinstance(corpus, dict) else None
    report.check(isinstance(cases, list), f"{relative}: cases 必须是数组")
    if not isinstance(cases, list):
        return

    report.behavior_case_count = len(cases)
    rules = contract["behavior_eval"]
    report.check(
        rules["min_cases"] <= len(cases) <= rules["max_cases"],
        f"{relative}: 用例数必须在 {rules['min_cases']}—{rules['max_cases']} 之间",
    )

    seen_ids: set[str] = set()
    categories: set[str] = set()
    for index, case in enumerate(cases):
        prefix = f"{relative}: cases[{index}]"
        if not isinstance(case, dict):
            report.check(False, f"{prefix} 必须是对象")
            continue
        case_id = case.get("id")
        report.check(
            isinstance(case_id, str) and bool(case_id.strip()),
            f"{prefix}.id 必须是非空字符串",
        )
        if isinstance(case_id, str) and case_id.strip():
            report.check(case_id not in seen_ids, f"{prefix}.id 重复：{case_id}")
            seen_ids.add(case_id)

        category = case.get("category")
        report.check(isinstance(category, str), f"{prefix}.category 必须是字符串")
        if isinstance(category, str):
            categories.add(category)

        prompt = case.get("prompt")
        report.check(
            isinstance(prompt, str) and bool(prompt.strip()),
            f"{prefix}.prompt 必须是非空字符串",
        )
        report.check(
            case.get("expect") in {"activate", "reject"},
            f"{prefix}.expect 必须是 activate 或 reject",
        )
        for field_name in ("must", "must_not"):
            values = case.get(field_name)
            report.check(
                isinstance(values, list)
                and all(isinstance(value, str) and value.strip() for value in values),
                f"{prefix}.{field_name} 必须是非空字符串数组",
            )
        report.check(
            isinstance(case.get("must"), list) and bool(case.get("must")),
            f"{prefix}.must 至少包含一项",
        )

    required_categories = set(rules["required_categories"])
    report.check(
        categories == required_categories,
        f"{relative}: category 必须完整覆盖 {sorted(required_categories)}，"
        f"实际为 {sorted(categories)}",
    )


def validate_skill_entry(skill_root: Path, report: Report) -> None:
    path = skill_root / "SKILL.md"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    data, error = parse_frontmatter(text)
    report.check(not error, f"SKILL.md: {error or 'frontmatter 可解析'}")
    report.check(data.get("name") == "me", "SKILL.md: name 必须为 me")
    description = data.get("description", "")
    report.check(bool(description.strip()), "SKILL.md: description 不能为空")
    report.check(
        len(description) <= 500,
        "SKILL.md: description 不能超过 500 个字符",
    )

    metadata = skill_root / "agents" / "openai.yaml"
    if metadata.is_file():
        metadata_text = metadata.read_text(encoding="utf-8")
        for field_name in ("display_name", "short_description", "default_prompt"):
            report.check(
                field_name in metadata_text,
                f"agents/openai.yaml: 缺少 interface.{field_name}",
            )


def validate_profile(skill_root: Path, profile_root: Path) -> Report:
    report = Report(skill_root=skill_root, profile_root=profile_root)
    contract = load_contract(skill_root, report)
    if contract is None:
        return report

    plugin_root = skill_root.parents[1]
    for relative in contract.get("plugin_required_files", []):
        report.check(
            (plugin_root / relative).is_file(),
            f"插件缺少必需文件：{relative}",
        )
    for relative in contract.get("profile_required_files", []):
        report.check(
            (profile_root / relative).is_file(),
            f"画像目录缺少必需文件：{relative}",
        )
    for relative in contract.get("required_directories", []):
        report.check(
            (profile_root / relative).is_dir(),
            f"画像目录缺少必需目录：{relative}",
        )

    required_visibility = contract["privacy"]["required_visibility_marker"]
    main_path = profile_root / "人物画像.md"
    if main_path.is_file():
        text = main_path.read_text(encoding="utf-8")
        validate_frontmatter(
            report,
            "人物画像.md",
            text,
            contract["profile_frontmatter_required"],
            required_visibility,
        )
        validate_required_sections(
            report,
            "人物画像.md",
            text,
            contract["main_required_sections"],
        )

    readme_path = profile_root / "README.md"
    if readme_path.is_file():
        text = readme_path.read_text(encoding="utf-8")
        validate_frontmatter(
            report,
            "README.md",
            text,
            contract["profile_frontmatter_required"],
            required_visibility,
        )
        validate_required_sections(
            report,
            "README.md",
            text,
            contract["readme_required_sections"],
        )

    domain_dir = profile_root / "专项档案"
    if domain_dir.is_dir():
        domain_files = sorted(domain_dir.glob("*.md"))
        report.check(bool(domain_files), "专项档案/: 至少需要一个 Markdown 专项档案")
        for path in domain_files:
            relative = str(path.relative_to(profile_root))
            text = path.read_text(encoding="utf-8")
            validate_frontmatter(
                report,
                relative,
                text,
                contract["domain_frontmatter_required"],
                required_visibility,
            )
            validate_section_groups(
                report,
                relative,
                text,
                contract["domain_required_section_groups"],
            )

    ignore_path = profile_root / ".gitignore"
    if ignore_path.is_file():
        ignored = {
            line.strip()
            for line in ignore_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        missing_patterns = [
            pattern
            for pattern in contract["privacy"]["required_gitignore_patterns"]
            if pattern not in ignored
        ]
        report.check(
            not missing_patterns,
            f".gitignore: 缺少隐私排除项 {', '.join(missing_patterns)}",
        )

    update_log = profile_root / "更新日志.md"
    if update_log.is_file():
        text = update_log.read_text(encoding="utf-8")
        log_dates = re.findall(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|", text, re.MULTILINE)
        report.check(bool(log_dates), "更新日志.md: 至少需要一条带日期的记录")

    validate_skill_entry(skill_root, report)
    validate_behavior_cases(skill_root, contract, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验人物画像 skill 的数据与行为契约。")
    parser.add_argument(
        "--skill-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Skill 根目录；默认为当前脚本上一级目录。",
    )
    parser.add_argument(
        "--profile-root",
        type=Path,
        default=Path(os.environ.get("PERSONA_PROFILE_ROOT", DEFAULT_PROFILE_ROOT)),
        help="人物画像数据目录；优先使用参数，其次 PERSONA_PROFILE_ROOT。",
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON。")
    args = parser.parse_args(argv)

    skill_root = args.skill_root.expanduser().resolve()
    profile_root = args.profile_root.expanduser().resolve()
    if not skill_root.is_dir() or not profile_root.is_dir():
        missing = []
        if not skill_root.is_dir():
            missing.append(f"Skill 目录不存在：{skill_root}")
        if not profile_root.is_dir():
            missing.append(f"画像目录不存在：{profile_root}")
        payload = {
            "ok": False,
            "skill_root": str(skill_root),
            "profile_root": str(profile_root),
            "errors": missing,
            "checks": 0,
            "behavior_case_count": 0,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    report = validate_profile(skill_root, profile_root)
    payload = {
        "ok": not report.errors,
        "skill_root": str(skill_root),
        "profile_root": str(profile_root),
        "checks": report.checks,
        "behavior_case_count": report.behavior_case_count,
        "errors": report.errors,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif report.errors:
        print(f"profile validation: {len(report.errors)} error(s)", file=sys.stderr)
        for error in report.errors:
            print(f"  FAIL  {error}", file=sys.stderr)
    else:
        print(
            f"profile validation: {report.checks} checks passed; "
            f"{report.behavior_case_count} behavior cases"
        )
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
