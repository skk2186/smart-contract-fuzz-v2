#!/usr/bin/env python3
"""把已有 Slither 属性 JSON、源码证据和编译 ABI 组装成 Agent 上下文。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PROJECTS = {
    "Request": {
        "report": ".tools/results/request-property.json",
        "artifact": ".tools/results/Request-Harness编译.json",
        "source_root": "sol/真实项目/Request",
        "contract": "EchidnaERC20CommerceEscrowWrapper",
    },
    "Immutable": {
        "report": ".tools/results/immutable-full-final.json",
        "artifact": ".tools/results/Immutable-Harness编译.json",
        "source_root": "sol/真实项目/Immutable",
        "contract": "ERC721PsiV2Echidna",
    },
    "Hokusai": {
        "report": "deepseek/结果/自主种子质量实验/Hokusai-Slither属性.json",
        "artifact": "deepseek/结果/自主种子质量实验/HokusaiToken-Harness编译.json",
        "source_root": "sol/真实项目/Hokusai",
        "contract": "EchidnaHokusaiToken",
    },
    "BeeStorage": {
        "report": "deepseek/结果/自主种子质量实验/BeeStorage-Slither属性.json",
        "artifact": "deepseek/结果/自主种子质量实验/BeeStorage-Harness编译.json",
        "source_root": "sol/真实项目/BeeStorage",
        "contract": "EchidnaSystemHarness",
    },
    "Drips": {
        "report": "deepseek/结果/自主种子质量实验/Drips-Slither属性.json",
        "artifact": "deepseek/结果/自主种子质量实验/Drips-Harness编译.json",
        "source_root": "sol/真实项目/DripsSCFuzzBench",
        "contract": "Echidna",
    },
    "Kink": {
        "report": "deepseek/结果/自主种子质量实验/Kink-Slither属性.json",
        "artifact": "deepseek/结果/自主种子质量实验/Kink-Harness编译.json",
        "source_root": "sol/真实项目/Kink",
        "contract": "KinkPoolEchidna",
    },
}
SEED_TYPES = re.compile(r"^(u?int)([0-9]*)$")
FIXED_BYTES_TYPES = re.compile(r"^bytes([1-9]|[12][0-9]|3[0-2])$")
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def read_json(path: str | Path) -> Any:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _resolve_source(project: str, reference: str) -> Path | None:
    raw = reference.split("#", 1)[0]
    path = Path(raw)
    choices = [ROOT / path]
    if not path.is_absolute():
        choices.append(ROOT / PROJECTS[project]["source_root"] / path)
    for candidate in choices:
        if candidate.is_file():
            return candidate
    return None


def source_excerpt(project: str, reference: str, limit: int = 4800) -> str | None:
    match = re.search(r"#(\d+)(?:-(\d+))?$", reference)
    path = _resolve_source(project, reference)
    if path is None or match is None:
        return None
    start = int(match.group(1))
    end = int(match.group(2) or start)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if start < 1 or start > len(lines):
        return None
    end = min(end, len(lines))
    excerpt = "\n".join(f"{n}: {lines[n - 1]}" for n in range(start, end + 1))
    return excerpt[:limit]


def _function_excerpt(project: str, signature: str, limit: int = 3000) -> str | None:
    tail = signature.rsplit(".", 1)[-1]
    name = tail.split("(", 1)[0]
    if not name:
        return None
    root = ROOT / PROJECTS[project]["source_root"]
    needle = re.compile(r"\bfunction\s+" + re.escape(name) + r"\s*\(")
    excluded = {"node_modules", "vendor", ".git", "out", "cache"}
    for path in root.rglob("*.sol"):
        if any(part in excluded for part in path.parts):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            if not needle.search(line):
                continue
            depth = 0
            opened = False
            end = min(i + 80, len(lines))
            for j in range(i, end):
                depth += lines[j].count("{") - lines[j].count("}")
                opened |= "{" in lines[j]
                if opened and depth <= 0:
                    end = j + 1
                    break
            excerpt = "\n".join(f"{n + 1}: {lines[n]}" for n in range(i, end))
            return excerpt[:limit]
    return None


def _abi_signature(entry: dict[str, Any]) -> str:
    return entry["name"] + "(" + ",".join(item["type"] for item in entry.get("inputs", [])) + ")"


def _seed_abi_supported(entry: dict[str, Any]) -> tuple[bool, str | None]:
    for item in entry.get("inputs", []):
        kind = item["type"]
        if (kind == "address" or kind == "bool" or SEED_TYPES.fullmatch(kind) or
                FIXED_BYTES_TYPES.fullmatch(kind)):
            continue
        return False, f"Echidna 原生序列化器暂未接入 ABI 类型 {kind}"
    return True, None


def _all_actions(prop: dict[str, Any]) -> list[dict[str, Any]]:
    out = list(prop.get("candidate_actions", []))
    out += list(prop.get("cross_contract", {}).get("candidate_actions", []))
    seen: set[str] = set()
    unique = []
    for action in out:
        signature = action.get("function", "")
        if signature and signature not in seen:
            seen.add(signature)
            unique.append(action)
    return unique


def _property_context(project: str, prop: dict[str, Any], report: dict[str, Any],
                      artifact: dict[str, Any]) -> dict[str, Any]:
    abi_functions = { _abi_signature(item): item for item in artifact["abi"]
                      if item.get("type") == "function" }
    by_name: dict[str, list[dict[str, Any]]] = {}
    for signature, entry in abi_functions.items():
        by_name.setdefault(entry["name"], []).append(entry)

    actions = []
    effect_catalog = report.get("effect_catalog", {})
    for action in _all_actions(prop):
        full_signature = action.get("function", "")
        short_signature = full_signature.rsplit(".", 1)[-1]
        abi_entry = abi_functions.get(short_signature)
        if abi_entry is None:
            same_name = by_name.get(short_signature.split("(", 1)[0], [])
            if len(same_name) == 1:
                abi_entry = same_name[0]
        supported, unsupported_reason = (False, "Slither 候选与 Harness ABI 未匹配")
        if abi_entry is not None:
            supported, unsupported_reason = _seed_abi_supported(abi_entry)
            if abi_entry.get("stateMutability") in {"view", "pure"}:
                supported, unsupported_reason = False, "只读入口不作为状态准备交易候选"
        evidence = []
        for effect_id in action.get("effect_ids", []):
            effect = effect_catalog.get(effect_id)
            if not effect:
                continue
            guards = []
            for guard in effect.get("guards", [])[:8]:
                guards.append({key: guard.get(key) for key in
                               ("kind", "expression", "branch", "variables_read", "source")})
            evidence.append({"state": effect.get("state"), "writer": effect.get("writer"),
                             "expression": effect.get("expression"),
                             "source": effect.get("source"), "guards": guards})
        actions.append({
            "function": full_signature,
            "abi_signature": _abi_signature(abi_entry) if abi_entry else None,
            "abi_inputs": [{"name": x.get("name", ""), "type": x["type"]}
                           for x in abi_entry.get("inputs", [])] if abi_entry else [],
            "state_mutability": abi_entry.get("stateMutability") if abi_entry else None,
            "payable": bool(action.get("payable", False)),
            "matched_states": action.get("matched_states", []),
            "environment_reads": action.get("environment_reads", []),
            "static_status": action.get("analysis_status"),
            "seed_compatible": supported,
            "seed_limitation": unsupported_reason,
            "source_excerpt": _function_excerpt(project, full_signature),
            "effect_evidence": evidence,
        })

    property_source = prop.get("source", "")
    property_signature = prop.get("property", "")
    property_name = property_signature.rsplit(".", 1)[-1].split("(", 1)[0]
    property_abi = abi_functions.get(property_signature.rsplit(".", 1)[-1])
    if property_abi is None:
        property_abi = next((entry for entry in abi_functions.values()
                             if entry.get("name") == property_name and
                             len(entry.get("inputs", [])) == len(
                                 prop.get("property_parameters", []))), None)
    assertion_trigger = None
    if prop.get("property_kind") == "assertion_test" and property_abi is not None:
        trigger_supported, trigger_limitation = _seed_abi_supported(property_abi)
        assertion_trigger = {
            "function": property_signature,
            "abi_signature": _abi_signature(property_abi),
            "abi_inputs": [{"name": item.get("name", ""), "type": item["type"]}
                           for item in property_abi.get("inputs", [])],
            "payable": property_abi.get("stateMutability") == "payable",
            "seed_compatible": trigger_supported,
            "seed_limitation": trigger_limitation,
            "source_excerpt": source_excerpt(project, property_source),
        }
    return {
        "property_id": prop.get("property_id"),
        "property": property_signature,
        "property_abi": _abi_signature(property_abi) if property_abi else None,
        "property_abi_inputs": ([{"name": item.get("name", ""), "type": item["type"]}
                                  for item in property_abi.get("inputs", [])]
                                 if property_abi else []),
        "property_kind": prop.get("property_kind", "boolean_property"),
        "assertion_sites": prop.get("assertion_sites", []),
        "assertion_trigger": assertion_trigger,
        "property_source": property_source,
        "property_predicate": source_excerpt(project, property_source),
        "analysis_contract": prop.get("analysis_contract"),
        "analysis_status": prop.get("analysis_status"),
        "context_status": prop.get("context_status"),
        "dependency_status": prop.get("dependency_status"),
        "read_states": prop.get("read_states", []),
        "property_write_states": prop.get("property_write_states", []),
        "environment_reads": prop.get("environment_reads", []),
        "read_sites": prop.get("read_sites", []),
        "candidate_actions": actions,
        "prerequisite_state_closure": prop.get("prerequisite_state_closure", []),
        "unknowns": prop.get("unknowns", []),
        "unresolved_effect_actions": prop.get("unresolved_effect_actions", []),
        "interpretation": prop.get("interpretation"),
    }


def load_project_context(project: str, property_ids: list[str] | None = None) -> dict[str, Any]:
    if project not in PROJECTS:
        raise ValueError(f"未知项目：{project}")
    report = read_json(PROJECTS[project]["report"])
    artifact = read_json(PROJECTS[project]["artifact"])
    selected = [p for p in report.get("properties", [])
                if property_ids is None or p.get("property_id") in property_ids]
    missing = set(property_ids or []) - {p.get("property_id") for p in selected}
    if missing:
        raise ValueError(f"属性 ID 不在 {project} 报告中：{sorted(missing)}")
    return {"project": project, "contract": PROJECTS[project]["contract"],
            "target": PROJECTS[project]["report"],
            "compiler": artifact.get("compiler"),
            "property_count": len(selected),
            "properties": [_property_context(project, p, report, artifact) for p in selected]}


def find_property(project: str, contains: str) -> str:
    report = read_json(PROJECTS[project]["report"])
    found = [p for p in report.get("properties", []) if contains in p.get("property", "")]
    if len(found) != 1:
        raise ValueError(f"{project}: 搜索条件 {contains!r} 命中 {len(found)} 条属性")
    return found[0]["property_id"]


def compact_for_agent(context: dict[str, Any]) -> dict[str, Any]:
    """在属性组内只保留一份相同 ABI 与函数源码，按属性保留关系证据。"""
    shared: dict[str, dict[str, Any]] = {}
    compact_properties = []
    common_fields = ("abi_inputs", "state_mutability", "payable", "seed_compatible",
                     "seed_limitation", "source_excerpt")
    property_fields = ("function", "abi_signature", "matched_states", "environment_reads",
                       "static_status", "seed_compatible", "seed_limitation", "effect_evidence")
    for prop in context["properties"]:
        actions = []
        for action in prop.get("candidate_actions", []):
            key = action["function"]
            if key not in shared:
                shared[key] = {field: action.get(field) for field in common_fields}
                shared[key]["function"] = action["function"]
            item = {field: action.get(field) for field in property_fields}
            item["source_context_id"] = key
            actions.append(item)
        compact_properties.append({**{key: value for key, value in prop.items()
                                    if key != "candidate_actions"},
                                   "candidate_actions": actions})
    return {key: value for key, value in context.items() if key != "properties"} | {
        "shared_function_contexts": shared,
        "properties": compact_properties,
    }
