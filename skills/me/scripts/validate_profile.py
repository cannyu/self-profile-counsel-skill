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


SCHEMA_VERSION = 3
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
    "required_module_ids",
    "health_required_submodules",
    "module_required_frontmatter",
    "module_required_sections",
    "migration_statuses",
    "record_types",
    "record_statuses",
    "confidence_levels",
    "sensitivity_levels",
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
    evidence_record_count: int = 0
    modules: set[str] = field(default_factory=set)

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
        "required_module_ids",
        "health_required_submodules",
        "module_required_frontmatter",
        "module_required_sections",
        "migration_statuses",
        "record_types",
        "record_statuses",
        "confidence_levels",
        "sensitivity_levels",
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


def validate_module_document(
    profile_root: Path,
    relative_path: str,
    module_id: str,
    contract: dict[str, Any],
    report: Report,
    *,
    submodule_id: str | None = None,
) -> None:
    path = profile_root / relative_path
    if not path.is_file():
        report.check(False, f"模块文档不存在：{relative_path}")
        return
    text = path.read_text(encoding="utf-8")
    data, error = parse_frontmatter(text)
    report.check(not error, f"{relative_path}: {error or 'frontmatter 可解析'}")
    if error:
        return

    required = list(contract["module_required_frontmatter"])
    if submodule_id is not None:
        required.append("submodule_id")
    missing = [field for field in required if not data.get(field)]
    report.check(
        not missing,
        f"{relative_path}: 模块 frontmatter 缺少字段 {', '.join(missing)}",
    )
    report.check(
        data.get("module_id") == module_id,
        f"{relative_path}: module_id 必须为 {module_id}",
    )
    if submodule_id is not None:
        report.check(
            data.get("submodule_id") == submodule_id,
            f"{relative_path}: submodule_id 必须为 {submodule_id}",
        )
    report.check(
        data.get("migration_status") in contract["migration_statuses"],
        f"{relative_path}: migration_status 无效",
    )
    report.check(
        bool(VERSION_RE.fullmatch(data.get("version", ""))),
        f"{relative_path}: version 必须是 1.0 或 v2.0 形式",
    )
    validate_date_value(report, data.get("last_updated"), f"{relative_path}.last_updated")
    validate_required_sections(
        report,
        relative_path,
        text,
        contract["module_required_sections"],
    )


def validate_profile_index(
    profile_root: Path,
    contract: dict[str, Any],
    report: Report,
) -> tuple[dict[str, dict[str, Any]], set[tuple[str, str]]]:
    relative = "profile.index.json"
    path = profile_root / relative
    if not path.is_file():
        report.check(False, f"画像目录缺少必需文件：{relative}")
        return {}, set()
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        report.check(False, f"{relative}: 无法解析 JSON：{error}")
        return {}, set()

    report.check(
        isinstance(index, dict) and index.get("schema_version") == SCHEMA_VERSION,
        f"{relative}: schema_version 必须为 {SCHEMA_VERSION}",
    )
    if not isinstance(index, dict):
        return {}, set()
    modules = index.get("modules")
    report.check(isinstance(modules, list), f"{relative}: modules 必须是数组")
    if not isinstance(modules, list):
        return {}, set()

    module_map: dict[str, dict[str, Any]] = {}
    submodule_map: set[tuple[str, str]] = set()
    for module_index, module in enumerate(modules):
        prefix = f"{relative}: modules[{module_index}]"
        if not isinstance(module, dict):
            report.check(False, f"{prefix} 必须是对象")
            continue
        module_id = module.get("id")
        report.check(
            isinstance(module_id, str) and bool(module_id.strip()),
            f"{prefix}.id 必须是非空字符串",
        )
        if not isinstance(module_id, str) or not module_id.strip():
            continue
        report.check(
            module_id not in module_map,
            f"{relative}: module id 重复：{module_id}",
        )
        module_map[module_id] = module
        report.modules.add(module_id)
        report.check(
            isinstance(module.get("name"), str) and bool(module["name"].strip()),
            f"{prefix}.name 必须是非空字符串",
        )
        report.check(
            module.get("migration_status") in contract["migration_statuses"],
            f"{prefix}.migration_status 无效",
        )
        report.check(
            module.get("sensitivity") in contract["sensitivity_levels"],
            f"{prefix}.sensitivity 无效",
        )

        module_path = module.get("path")
        report.check(
            isinstance(module_path, str) and bool(module_path.strip()),
            f"{prefix}.path 必须是非空字符串",
        )
        if isinstance(module_path, str) and module_path.strip():
            validate_module_document(
                profile_root,
                module_path,
                module_id,
                contract,
                report,
            )

        legacy_sources = module.get("legacy_sources")
        report.check(
            isinstance(legacy_sources, list)
            and all(
                isinstance(source, str) and source.strip()
                for source in legacy_sources
            ),
            f"{prefix}.legacy_sources 必须是非空字符串数组",
        )
        if isinstance(legacy_sources, list):
            for source in legacy_sources:
                if isinstance(source, str) and source.strip():
                    report.check(
                        (profile_root / source).is_file(),
                        f"{relative}: {module_id} 的 legacy source 不存在：{source}",
                    )

        submodules = module.get("submodules")
        report.check(
            isinstance(submodules, list) and bool(submodules),
            f"{prefix}.submodules 必须是数组",
        )
        if not isinstance(submodules, list):
            continue
        local_ids: set[str] = set()
        for submodule_index, submodule in enumerate(submodules):
            sub_prefix = f"{prefix}.submodules[{submodule_index}]"
            if not isinstance(submodule, dict):
                report.check(False, f"{sub_prefix} 必须是对象")
                continue
            submodule_id = submodule.get("id")
            report.check(
                isinstance(submodule_id, str) and bool(submodule_id.strip()),
                f"{sub_prefix}.id 必须是非空字符串",
            )
            if not isinstance(submodule_id, str) or not submodule_id.strip():
                continue
            report.check(
                submodule_id not in local_ids,
                f"{prefix}: submodule id 重复：{submodule_id}",
            )
            local_ids.add(submodule_id)
            submodule_map.add((module_id, submodule_id))
            submodule_path = submodule.get("path")
            if isinstance(submodule_path, str) and submodule_path.strip():
                validate_module_document(
                    profile_root,
                    submodule_path,
                    module_id,
                    contract,
                    report,
                    submodule_id=submodule_id,
                )

    required_modules = set(contract["required_module_ids"])
    report.check(
        set(module_map) == required_modules,
        f"{relative}: module 必须完整覆盖 {sorted(required_modules)}，"
        f"实际为 {sorted(module_map)}",
    )
    health = module_map.get("health_wellbeing", {})
    health_submodules = {
        submodule.get("id")
        for submodule in health.get("submodules", [])
        if isinstance(submodule, dict)
    }
    required_health = set(contract["health_required_submodules"])
    report.check(
        health_submodules == required_health,
        f"{relative}: health_wellbeing 必须包含 "
        f"{sorted(required_health)}，实际为 {sorted(str(item) for item in health_submodules)}",
    )
    return module_map, submodule_map


def validate_evidence(
    profile_root: Path,
    contract: dict[str, Any],
    module_map: dict[str, dict[str, Any]],
    submodule_map: set[tuple[str, str]],
    report: Report,
) -> None:
    schema_path = profile_root / "evidence" / "schema.json"
    if schema_path.is_file():
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            report.check(False, f"evidence/schema.json 无法读取：{error}")
        else:
            report.check(
                isinstance(schema, dict)
                and isinstance(schema.get("$schema"), str)
                and schema.get("type") == "object",
                "evidence/schema.json: 必须是有效的对象 schema",
            )

    relative = "evidence/ledger.json"
    path = profile_root / relative
    if not path.is_file():
        return
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        report.check(False, f"{relative}: 无法解析 JSON：{error}")
        return
    report.check(
        isinstance(ledger, dict) and ledger.get("schema_version") == SCHEMA_VERSION,
        f"{relative}: schema_version 必须为 {SCHEMA_VERSION}",
    )
    records = ledger.get("records") if isinstance(ledger, dict) else None
    report.check(isinstance(records, list), f"{relative}: records 必须是数组")
    if not isinstance(records, list):
        return
    report.evidence_record_count = len(records)
    seen_ids: set[str] = set()
    required_fields = {
        "id",
        "module",
        "submodule",
        "type",
        "statement",
        "source",
        "observed_at",
        "last_verified",
        "status",
        "confidence",
        "sensitivity",
        "allowed_uses",
        "linked_modules",
        "boundary",
    }
    for record_index, record in enumerate(records):
        prefix = f"{relative}: records[{record_index}]"
        if not isinstance(record, dict):
            report.check(False, f"{prefix} 必须是对象")
            continue
        missing = required_fields - set(record)
        report.check(not missing, f"{prefix} 缺少字段 {', '.join(sorted(missing))}")
        record_id = record.get("id")
        report.check(
            isinstance(record_id, str) and bool(record_id.strip()),
            f"{prefix}.id 必须是非空字符串",
        )
        if isinstance(record_id, str) and record_id.strip():
            report.check(record_id not in seen_ids, f"{prefix}.id 重复：{record_id}")
            seen_ids.add(record_id)

        module_id = record.get("module")
        submodule_id = record.get("submodule")
        report.check(
            module_id in module_map,
            f"{prefix}.module 不存在：{module_id}",
        )
        report.check(
            (module_id, submodule_id) in submodule_map,
            f"{prefix}.submodule 不属于模块：{module_id}/{submodule_id}",
        )
        for field_name, allowed in (
            ("type", contract["record_types"]),
            ("status", contract["record_statuses"]),
            ("confidence", contract["confidence_levels"]),
            ("sensitivity", contract["sensitivity_levels"]),
        ):
            report.check(
                record.get(field_name) in allowed,
                f"{prefix}.{field_name} 无效：{record.get(field_name)}",
            )
        for field_name in ("statement", "boundary"):
            report.check(
                isinstance(record.get(field_name), str)
                and bool(record[field_name].strip()),
                f"{prefix}.{field_name} 必须是非空字符串",
            )
        source = record.get("source")
        report.check(
            isinstance(source, dict)
            and isinstance(source.get("kind"), str)
            and isinstance(source.get("location"), str),
            f"{prefix}.source 必须包含 kind 和 location",
        )
        for field_name in ("observed_at", "last_verified"):
            validate_date_value(
                report,
                record.get(field_name),
                f"{prefix}.{field_name}",
            )
        allowed_uses = record.get("allowed_uses")
        report.check(
            isinstance(allowed_uses, list)
            and bool(allowed_uses)
            and all(isinstance(value, str) and value.strip() for value in allowed_uses),
            f"{prefix}.allowed_uses 必须是非空字符串数组",
        )
        linked = record.get("linked_modules")
        report.check(
            isinstance(linked, list)
            and all(isinstance(value, str) for value in linked),
            f"{prefix}.linked_modules 必须是字符串数组",
        )
        if isinstance(linked, list):
            for linked_module in linked:
                report.check(
                    linked_module in module_map,
                    f"{prefix}.linked_modules 含未知模块：{linked_module}",
                )


def validate_date_value(report: Report, value: Any, path: str) -> None:
    valid = isinstance(value, str) and bool(DATE_RE.fullmatch(value))
    if valid:
        try:
            date.fromisoformat(value)
        except ValueError:
            valid = False
    report.check(valid, f"{path} 必须是合法的 YYYY-MM-DD 日期")


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

    module_map, submodule_map = validate_profile_index(
        profile_root,
        contract,
        report,
    )
    validate_evidence(
        profile_root,
        contract,
        module_map,
        submodule_map,
        report,
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
            "evidence_record_count": 0,
            "modules": [],
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
        "evidence_record_count": report.evidence_record_count,
        "modules": sorted(report.modules),
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
            f"{report.behavior_case_count} behavior cases; "
            f"{report.evidence_record_count} evidence records"
        )
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
