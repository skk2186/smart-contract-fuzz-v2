#!/usr/bin/env python3
"""把已有 Slither 属性 JSON、源码证据和编译 ABI 组装成 Agent 上下文。"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from 项目配置 import register_project_profiles


ROOT = Path(__file__).resolve().parents[2]
PROJECTS = {
    "OpenNFTs": {
        "report": "deepseek/结果/通用依赖泛化验证/OpenNFTs-Slither属性.json",
        "artifact": "deepseek/结果/通用依赖泛化验证/OpenNFTs-Harness编译.json",
        "source_root": "sol/真实项目/OpenNFTs",
        "contract": "OpenAutoMarketExFuzz",
    },
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
register_project_profiles(PROJECTS)
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
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            # An inaccessible repository-root mirror can still have a readable
            # project-local copy under source_root (for example on mounted WSL paths).
            continue
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


def _balanced_end(text: str, opening: int, left: str = "{", right: str = "}") -> int | None:
    depth = 0
    quote = None
    escaped = False
    line_comment = False
    block_comment = False
    index = opening
    while index < len(text):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
        elif block_comment:
            if char == "*" and following == "/":
                block_comment = False
                index += 1
        elif quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char == "/" and following == "/":
            line_comment = True
            index += 1
        elif char == "/" and following == "*":
            block_comment = True
            index += 1
        elif char in {"'", '"'}:
            quote = char
        elif char == left:
            depth += 1
        elif char == right:
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return None


def _split_parameters(text: str) -> list[str]:
    parts, start, depth = [], 0, 0
    for index, char in enumerate(text):
        if char in "([<{":
            depth += 1
        elif char in ")]}>" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail or parts:
        parts.append(tail)
    return parts


def _canonical_source_type(parameter: str) -> str:
    parameter = re.sub(r"\b(memory|storage|calldata|payable)\b", " ", parameter).strip()
    tokens = parameter.split()
    if not tokens:
        return ""
    raw = tokens[0]
    if raw == "uint":
        return "uint256"
    if raw == "int":
        return "int256"
    if raw == "byte":
        return "bytes1"
    return raw


@lru_cache(maxsize=16)
def _source_functions(project: str, *, include_dependencies: bool = True) -> list[dict[str, Any]]:
    """提取源码中的合约函数；保留合约边界，避免同名函数误匹配。"""
    root = ROOT / PROJECTS[project]["source_root"]
    excluded = {"node_modules", "vendor", ".git", "out", "cache"}
    if not include_dependencies:
        excluded |= {"lib", "lib64", "dependencies", "deps"}
    found: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.sol")):
        if any(part in excluded for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for contract_match in re.finditer(
                r"\b(?:contract|library|interface)\s+([A-Za-z_][A-Za-z0-9_]*)[^{}]*\{", text):
            contract_open = text.find("{", contract_match.start())
            contract_end = _balanced_end(text, contract_open)
            if contract_end is None:
                continue
            contract_text = text[contract_open + 1:contract_end - 1]
            constructor_source = None
            constructor_match = re.search(r"\bconstructor\s*\(", contract_text)
            if constructor_match:
                constructor_paren = contract_text.find("(", constructor_match.start())
                constructor_paren_end = _balanced_end(contract_text, constructor_paren, "(", ")")
                if constructor_paren_end is not None:
                    constructor_brace = contract_text.find("{", constructor_paren_end)
                    if constructor_brace >= 0:
                        constructor_end = _balanced_end(contract_text, constructor_brace)
                        if constructor_end is not None:
                            absolute_start = contract_open + 1 + constructor_match.start()
                            absolute_end = contract_open + 1 + constructor_end
                            first_line = text.count("\n", 0, absolute_start) + 1
                            constructor_source = "\n".join(
                                f"{line_number}: {line}" for line_number, line in
                                enumerate(text[absolute_start:absolute_end].splitlines(), first_line))
            for function_match in re.finditer(
                    r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", contract_text):
                parameters_open = contract_text.find("(", function_match.start())
                parameters_end = _balanced_end(contract_text, parameters_open, "(", ")")
                if parameters_end is None:
                    continue
                parameters = _split_parameters(contract_text[parameters_open + 1:parameters_end - 1])
                types = [_canonical_source_type(item) for item in parameters]
                delimiter = parameters_end
                while delimiter < len(contract_text) and contract_text[delimiter] not in "{;":
                    delimiter += 1
                if delimiter >= len(contract_text):
                    continue
                end = (delimiter + 1 if contract_text[delimiter] == ";" else
                       _balanced_end(contract_text, delimiter))
                if end is None:
                    continue
                absolute_start = contract_open + 1 + function_match.start()
                absolute_end = contract_open + 1 + end
                first_line = text.count("\n", 0, absolute_start) + 1
                excerpt = "\n".join(
                    f"{line_number}: {line}" for line_number, line in
                    enumerate(text[absolute_start:absolute_end].splitlines(), first_line))
                found.append({"contract": contract_match.group(1),
                              "name": function_match.group(1),
                              "types": types,
                              "signature": function_match.group(1) + "(" + ",".join(types) + ")",
                              "source": excerpt,
                              "body": contract_text[function_match.start():end],
                              "contract_body": contract_text,
                              "constructor_source": constructor_source,
                              "path": str(path)})
    return found


def _resolve_source_function(functions: list[dict[str, Any]], contract_name: str | None,
                             signature: str) -> dict[str, Any] | None:
    name = signature.split("(", 1)[0].rsplit(".", 1)[-1]
    wanted = signature[signature.find("("):] if "(" in signature else None
    candidates = [item for item in functions if item["name"] == name and
                  (wanted is None or item["signature"].endswith(wanted))]
    if contract_name:
        exact_contract = [item for item in candidates if item["contract"] == contract_name]
        if len(exact_contract) == 1:
            return exact_contract[0]
        if exact_contract:
            return None
    return candidates[0] if len(candidates) == 1 else None


def _function_excerpt(project: str, signature: str, limit: int = 3000,
                      abi_signature: str | None = None) -> str | None:
    parts = signature.split(".")
    contract_name = parts[-2] if len(parts) > 1 else None
    wanted = abi_signature or parts[-1]
    function = _resolve_source_function(_source_functions(project), contract_name, wanted)
    return function["source"][:limit] if function else None


def _source_call_chain(project: str, signature: str, abi_signature: str | None,
                       *, max_depth: int = 4, max_chars: int = 8000) -> list[dict[str, Any]]:
    """提供源码可解析的外部调用链；未解析的 receiver 保留为未知证据。"""
    functions = _source_functions(project)
    parts = signature.split(".")
    root_contract = parts[-2] if len(parts) > 1 else None
    root_signature = abi_signature or parts[-1]
    root = _resolve_source_function(functions, root_contract, root_signature)
    if not root:
        return []
    by_contract = {item["contract"] for item in functions}
    queue = [(root, 0, None)]
    seen: set[tuple[str, str]] = set()
    output = []
    used_chars = 0
    while queue and len(output) < 12:
        current, depth, caller = queue.pop(0)
        key = (current["contract"], current["signature"])
        if key in seen:
            continue
        seen.add(key)
        contract_body = current["contract_body"]
        # Discover contract-typed storage variables, then local contract-typed values.
        declarations = re.findall(
            r"\b([A-Z][A-Za-z0-9_]*)\s*(?:\[[^\]]*\])?\s+"
            r"(?:(?:public|private|internal|external|constant|immutable)\s+)*"
            r"([A-Za-z_][A-Za-z0-9_]*)\b", contract_body)
        local_declarations = re.findall(
            r"\b([A-Z][A-Za-z0-9_]*)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=", current["body"])
        types_by_variable = {variable: type_name for type_name, variable in
                             [*declarations, *local_declarations]
                             if type_name in by_contract}
        state_lines = [f"{name}: {type_name}" for name, type_name in
                       sorted(types_by_variable.items())]
        constructor = current.get("constructor_source")
        record = {"contract": current["contract"], "function": current["signature"],
                  "called_from": caller,
                  "contract_typed_variables": state_lines,
                  "constructor_source": constructor,
                  "source_excerpt": current["source"]}
        size = len(json.dumps(record, ensure_ascii=False))
        if used_chars + size > max_chars and output:
            break
        output.append(record)
        used_chars += size
        if depth >= max_depth:
            continue
        for call in re.finditer(
                r"(?P<receiver>[A-Za-z_][A-Za-z0-9_]*(?:\s*\[[^\]]+\])?)\s*\.\s*"
                r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
                r"(?:\s*\.\s*(?:value|gas)\s*\([^)]*\))*\s*\(", current["body"]):
            receiver = call.group("receiver").split("[", 1)[0].strip()
            target_contract = types_by_variable.get(receiver)
            if not target_contract:
                continue
            arguments_open = call.end() - 1
            arguments_end = _balanced_end(current["body"], arguments_open, "(", ")")
            if arguments_end is None:
                continue
            argument_text = current["body"][arguments_open + 1:arguments_end - 1].strip()
            argument_count = len(_split_parameters(argument_text)) if argument_text else 0
            matches = [item for item in functions if item["contract"] == target_contract and
                       item["name"] == call.group("name") and
                       len(item["types"]) == argument_count]
            if len(matches) == 1:
                queue.append((matches[0], depth + 1,
                              f"{current['contract']}.{current['signature']} → "
                              f"{target_contract}.{matches[0]['signature']} ({receiver})"))
    return output


def _constructor_excerpt(project: str, source: str, limit: int = 3200) -> str | None:
    """从 Harness 原始源码提取构造函数，供初始状态推断使用。"""
    path = _resolve_source(project, source)
    if path is None:
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"\bconstructor\s*\([^)]*\)[^{]*\{", text)
    if not match:
        return None
    start = match.start()
    depth = 0
    for index in range(match.end() - 1, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1][:limit]
    return text[start:start + limit]


def _abi_signature(entry: dict[str, Any]) -> str:
    return entry["name"] + "(" + ",".join(item["type"] for item in entry.get("inputs", [])) + ")"


def _seed_abi_supported(entry: dict[str, Any]) -> tuple[bool, str | None]:
    def supported_type(kind: str) -> bool:
        array_match = re.fullmatch(r"(.+)\[\]", kind)
        if array_match:
            return bool(SEED_TYPES.fullmatch(array_match.group(1)))
        return (kind == "string" or kind == "address" or kind == "bool" or
                bool(SEED_TYPES.fullmatch(kind)) or
                bool(FIXED_BYTES_TYPES.fullmatch(kind)))

    for item in entry.get("inputs", []):
        kind = item["type"]
        if supported_type(kind):
            continue
        return False, f"Echidna 原生序列化器暂未接入 ABI 类型 {kind}"
    return True, None


def _abi_argument_ranges(entry: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    for item in (entry or {}).get("inputs", []):
        kind = str(item.get("type") or "")
        match = re.fullmatch(r"(u?)int([0-9]*)", kind)
        if not match:
            continue
        bits = int(match.group(2) or 256)
        signed = not bool(match.group(1))
        rows.append({"name": item.get("name"), "type": kind,
                     "minimum": -(1 << (bits - 1)) if signed else 0,
                     "maximum": (1 << (bits - 1)) - 1 if signed else (1 << bits) - 1,
                     "source": "ABI integer type"})
    return rows


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
                               ("kind", "expression", "branch", "variables_read",
                                "state_reads", "data_dependencies", "predicate_calls",
                                "predicate_logic", "source")})
            evidence.append({"state": effect.get("state"), "writer": effect.get("writer"),
                             "expression": effect.get("expression"),
                             "source": effect.get("source"), "guards": guards})
        actions.append({
            "function": full_signature,
            "abi_signature": _abi_signature(abi_entry) if abi_entry else None,
            "abi_inputs": [{"name": x.get("name", ""), "type": x["type"]}
                           for x in abi_entry.get("inputs", [])] if abi_entry else [],
            "argument_ranges": _abi_argument_ranges(abi_entry),
            "state_mutability": abi_entry.get("stateMutability") if abi_entry else None,
            "payable": bool(action.get("payable", False)),
            "matched_states": action.get("matched_states", []),
            "environment_reads": action.get("environment_reads", []),
            "static_status": action.get("analysis_status"),
            "seed_compatible": supported,
            "seed_limitation": unsupported_reason,
            "source_excerpt": _function_excerpt(
                project, full_signature, abi_signature=_abi_signature(abi_entry) if abi_entry else None),
            "source_call_chain": _source_call_chain(
                project, full_signature, _abi_signature(abi_entry) if abi_entry else None),
            "effect_evidence": evidence,
        })

    # Attach helper effects only when the public action source visibly calls the
    # corresponding helper. This is a candidate relation, not a proof of runtime
    # reachability or object aliasing.
    for action in actions:
        excerpt = action.get("source_excerpt") or ""
        helper_effects = []
        for effect in effect_catalog.values():
            writer = effect.get("writer", "")
            helper = writer.rsplit(".", 1)[-1].split("(", 1)[0]
            if helper and helper != action["function"].rsplit(".", 1)[-1].split("(", 1)[0]:
                if re.search(r"\b" + re.escape(helper) + r"\s*\(", excerpt):
                    helper_effects.append({"state": effect.get("state"),
                                           "writer": writer,
                                           "source": effect.get("source")})
        action["related_helper_effects"] = helper_effects[:16]

    producers: dict[str, list[dict[str, str]]] = {}
    action_requirements: dict[str, set[str]] = {}
    for action in actions:
        action_key = action["abi_signature"] or action["function"]
        effects = action.get("effect_evidence", []) + action.get("related_helper_effects", [])
        for effect in effects:
            state = effect.get("state")
            if isinstance(state, str):
                producer = {"function": action_key,
                            "evidence": effect.get("source") or effect.get("writer", "")}
                if producer not in producers.setdefault(state, []):
                    producers[state].append(producer)
        action_requirements[action_key] = {
            state for effect in action.get("effect_evidence", [])
            for guard in effect.get("guards", [])
            for state in guard.get("state_reads", []) if isinstance(state, str)}
    for action in actions:
        guards = [guard for effect in action.get("effect_evidence", [])
                  for guard in effect.get("guards", [])]
        required: dict[str, list[dict[str, Any]]] = {}
        for guard in guards:
            for state in guard.get("state_reads", []):
                if isinstance(state, str):
                    required.setdefault(state, []).append({
                        "expression": guard.get("expression"),
                        "predicate_calls": guard.get("predicate_calls", []),
                        "source": guard.get("source")})
        action["prerequisite_dependencies"] = [
            {"required_state": state,
             "guard_evidence": evidence[:3],
             "candidate_producers": [
                 {**producer,
                  "producer_guard_reads_same_state": state in action_requirements.get(
                      producer["function"], set())}
                 for producer in producers.get(state, [])
                 if producer["function"] != (action["abi_signature"] or action["function"])][:8],
             "resolution": "static_candidate_only"}
            for state, evidence in required.items()]

    constructor_excerpt = _constructor_excerpt(project, prop.get("source", ""))
    constructor_actions = []
    if constructor_excerpt:
        for action in actions:
            name = action["function"].rsplit(".", 1)[-1].split("(", 1)[0]
            if re.search(r"\b" + re.escape(name) + r"\s*\(", constructor_excerpt):
                constructor_actions.append(action["abi_signature"] or action["function"])

    slither_action_count = len(actions)
    fallback_action_count = 0
    action_inventory_source = "slither_dependency_candidates"
    if not any(action.get("seed_compatible") for action in actions):
        # Keep the property in the Agent pipeline when Slither cannot link a writer
        # to the observed state. The fallback is generic: all serializable, mutating
        # Harness ABI entries, with source excerpts for Agent A to inspect. It does
        # not prescribe a path, order, sender, or argument value.
        property_tail = prop.get("property", "").rsplit(".", 1)[-1]
        fallback_actions = []
        for signature, abi_entry in abi_functions.items():
            if signature == property_tail or abi_entry.get("stateMutability") in {"view", "pure"}:
                continue
            supported, unsupported_reason = _seed_abi_supported(abi_entry)
            if not supported:
                continue
            full_signature = f"{PROJECTS[project]['contract']}.{signature}"
            fallback_actions.append({
                "function": full_signature,
                "abi_signature": signature,
                "abi_inputs": [{"name": item.get("name", ""), "type": item["type"]}
                               for item in abi_entry.get("inputs", [])],
                "state_mutability": abi_entry.get("stateMutability"),
                "payable": abi_entry.get("stateMutability") == "payable",
                "matched_states": [],
                "environment_reads": [],
                "static_status": "abi_fallback_no_slither_writer_match",
                "seed_compatible": True,
                "seed_limitation": "No Slither write mapping; inspect source.",
                "source_excerpt": _function_excerpt(project, full_signature, limit=500,
                                                    abi_signature=signature),
                "source_call_chain": _source_call_chain(project, full_signature, signature),
                "effect_evidence": [],
                "action_source": "generic_abi_fallback",
            })
        if fallback_actions:
            actions = fallback_actions
            fallback_action_count = len(fallback_actions)
            action_inventory_source = "generic_abi_fallback_slither_relation_unresolved"

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
            "argument_ranges": _abi_argument_ranges(property_abi),
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
        "constructor_excerpt": constructor_excerpt,
        "constructor_actions": constructor_actions,
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
        "action_inventory_source": action_inventory_source,
        "slither_action_count": slither_action_count,
        "abi_fallback_action_count": fallback_action_count,
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


def compact_effect_evidence(effects: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """保留每个效果和所有不同守卫，移除跨状态效果重复记录的相同守卫。"""
    compact_effects = []
    unique_guards: dict[str, dict[str, Any]] = {}
    for effect in effects:
        compact_effects.append({field: value for field, value in effect.items()
                                if field != "guards"})
        for guard in effect.get("guards", []):
            guard_key = json.dumps(guard, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"))
            unique_guards.setdefault(guard_key, guard)
    return {"effect_evidence": compact_effects,
            "action_guard_evidence": list(unique_guards.values())}


def _focused_actions(prop: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    actions = list(prop.get("candidate_actions", []))
    if not actions:
        return actions, {"method": "no_candidate_actions", "before": 0, "after": 0}
    target_states = set(prop.get("read_states", [])) | set(prop.get("property_write_states", []))
    action_states = {
        str(action.get("abi_signature") or action.get("function")): {
            str(effect.get("state")) for effect in action.get("effect_evidence", [])
            if effect.get("state")}
        for action in actions}
    frequency: dict[str, int] = {}
    for states in action_states.values():
        for state in states:
            frequency[state] = frequency.get(state, 0) + 1
    common_threshold = max(3, (len(actions) + 1) // 2)
    common_states = {state for state, count in frequency.items()
                     if count >= common_threshold}
    focused_states = target_states - common_states
    if not focused_states:
        return actions, {"method": "evidence_not_selective_keep_all",
                         "before": len(actions), "after": len(actions),
                         "common_state_threshold": common_threshold,
                         "common_states": sorted(common_states),
                         "unknown": "no state was selective enough to safely prune actions"}
    trigger = (prop.get("assertion_trigger") or {}).get("abi_signature")
    kept = [action for action in actions
            if action_states.get(str(action.get("abi_signature") or action.get("function")), set())
            & focused_states or action.get("abi_signature") == trigger]
    if not kept:
        kept = actions
        method = "evidence_not_selective_keep_all"
    else:
        method = "exact_effect_state_excluding_frequent_shared_matches"
    property_name = str(prop.get("property") or "").rsplit(".", 1)[-1]
    kept.sort(key=lambda action: 0 if action.get("abi_signature") == property_name else 1)
    return kept, {"method": method, "before": len(actions), "after": len(kept),
                  "focused_states": sorted(focused_states),
                  "frequent_shared_states_not_used_for_action_selection": sorted(common_states),
                  "excluded_signatures": [str(action.get("abi_signature") or action.get("function"))
                                          for action in actions if action not in kept],
                  "unknowns_preserved": list(prop.get("unknowns", []))}


def _internal_helper_contexts(project: str, actions: list[dict[str, Any]], *,
                              max_helpers: int = 12, max_depth: int = 2) -> list[dict[str, Any]]:
    """Resolve directly called local helpers while preserving source provenance."""
    if project not in PROJECTS:
        return []
    functions = _source_functions(project, include_dependencies=False)
    queue: list[tuple[dict[str, Any], int, str]] = []
    for action in actions:
        full = str(action.get("function") or "")
        parts = full.split(".")
        contract = parts[-2] if len(parts) > 1 else None
        signature = action.get("abi_signature") or parts[-1]
        root = _resolve_source_function(functions, contract, str(signature))
        if root:
            queue.append((root, 0, str(signature)))
    helpers = []
    seen = set()
    reserved = {"if", "for", "while", "require", "assert", "revert", "return",
                "emit", "new", "delete", "keccak256", "abi", "type", "unchecked"}
    while queue and len(helpers) < max_helpers:
        current, depth, root_signature = queue.pop(0)
        if depth >= max_depth:
            continue
        names = []
        for call in re.finditer(r"(?<![.A-Za-z0-9_])([A-Za-z_]\w*)\s*\(", current["body"]):
            name = call.group(1)
            if name not in reserved and name not in names:
                names.append(name)
        for name in names:
            candidates = [item for item in functions if item["name"] == name]
            if len(candidates) != 1:
                continue
            helper = candidates[0]
            key = (helper["contract"], helper["signature"])
            if key in seen or (helper["contract"], helper["signature"]) == (
                    current["contract"], current["signature"]):
                continue
            seen.add(key)
            helpers.append({"function": helper["contract"] + "." + helper["signature"],
                            "called_from": current["contract"] + "." + current["signature"],
                            "root_action": root_signature,
                            "source": helper["source"][:1800],
                            "source_path": helper.get("path")})
            queue.append((helper, depth + 1, root_signature))
            if len(helpers) >= max_helpers:
                break
    return helpers


def compact_for_agent(context: dict[str, Any]) -> dict[str, Any]:
    """Deduplicate repeated source and omit noisy actions without direct state evidence."""
    shared: dict[str, dict[str, Any]] = {}
    compact_properties = []
    common_fields = ("abi_inputs", "argument_ranges", "numeric_guard_evidence",
                     "state_mutability", "payable", "seed_compatible",
                     "seed_limitation", "source_excerpt", "prerequisite_dependencies",
                     "related_helper_effects", "source_call_chain")
    property_fields = ("function", "abi_signature", "matched_states", "environment_reads",
                       "static_status", "seed_compatible", "effect_evidence",
                       "numeric_guard_evidence",
                       "prerequisite_dependencies", "related_helper_effects",
                       "source_call_chain")
    for prop in context["properties"]:
        focused_actions, focus_metadata = _focused_actions(prop)
        actions = []
        for action in focused_actions:
            key = action["function"]
            if key not in shared:
                shared[key] = {field: action.get(field) for field in common_fields}
                shared[key]["function"] = action["function"]
            item = {field: action.get(field) for field in property_fields}
            item["source_context_id"] = key
            item.update(compact_effect_evidence(action.get("effect_evidence", [])))
            actions.append(item)
        compact_property = {**{key: value for key, value in prop.items()
                               if key != "candidate_actions"},
                            "candidate_actions": actions,
                            "context_focus": focus_metadata}
        helpers = _internal_helper_contexts(str(context.get("project") or ""), focused_actions)
        if helpers:
            compact_property["direct_internal_helper_contexts"] = helpers
        compact_properties.append(compact_property)
    compact_context = {key: value for key, value in context.items()
                       if key != "properties"}
    compact_context["shared_function_contexts"] = shared
    compact_context["properties"] = compact_properties
    return compact_context
