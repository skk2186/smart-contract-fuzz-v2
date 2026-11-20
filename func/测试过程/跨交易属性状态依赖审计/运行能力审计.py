#!/usr/bin/env python3
"""Frozen, bounded Anvil audit of V2 cross-transaction dependency handling."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from web3 import Web3


ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "func/功能"), str(ROOT / "deepseek"),
                str(ROOT / "func/测试过程/SCFuzzBench公开项目接入")]
RESULT_ROOT = ROOT / "func/测试过程/跨交易属性状态依赖审计/结果"
RUN_ROOT = RESULT_ROOT / "20261120"
FREEZE = RUN_ROOT / "00-实验冻结方案.json"
ORACLE_PLAN = RUN_ROOT / "00-独立Oracle计划.json"
SOLC = Path("/home/skk/.solc-select/artifacts/solc-0.8.28/solc-0.8.28")
DEPLOYER = "0x0000000000000000000000000000000000030000"
SENDERS = [f"0x{i:040x}" for i in range(0x10000, 0x60000, 0x10000)]
PROPERTY_SENDER = SENDERS[0]
CONTRACT_ADDRESS = "0xA647ff3c36cFab592509E13860ab8c4F28781a66"
HISTORICAL_WALLET = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Wallet02Refund/Phase30B-20261119/03-P0-P1配对验证结果.json"
WALLET_ORACLE = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Wallet02Refund/Phase30B-20261119/diagnostic-oracle/manual-oracle-result.json"
PIGFOX_INPUT = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/Inputs/E1-AgentAB-raw-seed.json"
PIGFOX_COMPAT = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/CompatibilityHarness"
PIGFOX_REPORT = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-20261120/Phase32PigfoxRWADemo/分析报告.json"

TASK_SPECS: dict[str, dict[str, Any]] = {
    "BWorkflow": {
        "project": "AuditBWorkflow", "contract": "WorkflowHarness",
        "source": "sol/单合约测试/StateDependencyAuditBWorkflow/WorkflowHarness.sol",
        "property": "echidna_workflow_respects_limit", "property_id": "audit-b-workflow",
        "goal": {"kind": "workflow_stage", "stage_getter": "stage()",
                 "completed_getter": "completedAmount()", "stage": 3,
                 "completed_min": 1},
        "oracle_steps": [
            {"function": "createTask()", "arguments": [], "sender": SENDERS[0], "value_wei": "0"},
            {"function": "configureTask(uint256)", "arguments": [5], "sender": SENDERS[0], "value_wei": "0"},
            {"function": "executeTask(uint256)", "arguments": [3], "sender": SENDERS[1], "value_wei": "0"},
        ],
        "oracle_getters": [
            {"function": "stage()", "arguments": []},
            {"function": "executionLimit()", "arguments": []},
            {"function": "completedAmount()", "arguments": []},
        ],
        "rename_map": {"createTask()": "openOrder()",
                       "configureTask(uint256)": "setQuota(uint256)",
                       "executeTask(uint256)": "applyOrder(uint256)"},
        "variant": "BWorkflowRenamed",
    },
    "BWorkflowRenamed": {
        "project": "AuditBWorkflowRenamed", "contract": "WorkOrderHarness",
        "source": "sol/单合约测试/StateDependencyAuditBWorkflow/WorkflowHarness-Renamed.sol",
        "property": "echidna_order_value_within_quota", "property_id": "audit-b-workflow-renamed",
        "goal": {"kind": "workflow_stage", "stage_getter": "phase()",
                 "completed_getter": "appliedValue()", "stage": 3,
                 "completed_min": 1},
        "oracle_steps": [
            {"function": "openOrder()", "arguments": [], "sender": SENDERS[0], "value_wei": "0"},
            {"function": "setQuota(uint256)", "arguments": [5], "sender": SENDERS[0], "value_wei": "0"},
            {"function": "applyOrder(uint256)", "arguments": [3], "sender": SENDERS[1], "value_wei": "0"},
        ],
        "oracle_getters": [
            {"function": "phase()", "arguments": []},
            {"function": "quota()", "arguments": []},
            {"function": "appliedValue()", "arguments": []},
        ],
    },
    "CMsgSender": {
        "project": "AuditCMsgSender", "contract": "MsgSenderDelegationHarness",
        "source": "sol/单合约测试/StateDependencyAuditCMsgSender/MsgSenderDelegationHarness.sol",
        "property": "echidna_delegated_execution_is_bounded", "property_id": "audit-c-msg-sender",
        "goal": {"kind": "delegated_execution", "owner": SENDERS[0],
                 "operator": SENDERS[1], "executed_getter": "executedFor(address)",
                 "deposit_getter": "depositedCredit(address)",
                 "available_getter": "availableCredit(address)",
                 "authorization_getter": "authorizedOperator(address)",
                 "amount": 1},
        "oracle_steps": [
            {"function": "fundCredit()", "arguments": [], "sender": SENDERS[0], "value_wei": "1000000000000000000"},
            {"function": "authorizeOperator(address)", "arguments": [SENDERS[1]], "sender": SENDERS[0], "value_wei": "0"},
            {"function": "executeFor(address,uint256)", "arguments": [SENDERS[0], 1], "sender": SENDERS[1], "value_wei": "0"},
        ],
        "oracle_getters": [
            {"function": "depositedCredit(address)", "arguments": [SENDERS[0]]},
            {"function": "availableCredit(address)", "arguments": [SENDERS[0]]},
            {"function": "authorizedOperator(address)", "arguments": [SENDERS[0]]},
            {"function": "executedFor(address)", "arguments": [SENDERS[0]]},
        ],
    },
    "DAllowance": {
        "project": "AuditDAllowance", "contract": "AllowanceHarness",
        "source": "sol/单合约测试/StateDependencyAuditDAllowance/AllowanceHarness.sol",
        "property": "echidna_delegated_spend_is_bounded", "property_id": "audit-d-allowance",
        "goal": {"kind": "delegated_spend", "owner": SENDERS[0],
                 "spender": SENDERS[1], "recipient": SENDERS[2], "amount": 4,
                 "balance_getter": "balanceOf(address)",
                 "allowance_getter": "allowance(address,address)",
                 "grant_getter": "totalGranted(address,address)",
                 "spent_getter": "delegatedSpent(address,address)",
                 "supply_getter": "totalSupply()"},
        "oracle_steps": [
            {"function": "mint(address,uint256)", "arguments": [SENDERS[0], 10], "sender": SENDERS[0], "value_wei": "0"},
            {"function": "approve(address,uint256)", "arguments": [SENDERS[1], 7], "sender": SENDERS[0], "value_wei": "0"},
            {"function": "transferFrom(address,address,uint256)", "arguments": [SENDERS[0], SENDERS[2], 4], "sender": SENDERS[1], "value_wei": "0"},
        ],
        "oracle_getters": [
            {"function": "balanceOf(address)", "arguments": [SENDERS[0]]},
            {"function": "balanceOf(address)", "arguments": [SENDERS[1]]},
            {"function": "allowance(address,address)", "arguments": [SENDERS[0], SENDERS[1]]},
            {"function": "totalGranted(address,address)", "arguments": [SENDERS[0], SENDERS[1]]},
            {"function": "delegatedSpent(address,address)", "arguments": [SENDERS[0], SENDERS[1]]},
            {"function": "totalSupply()", "arguments": []},
        ],
    },
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def freeze_inputs() -> None:
    if FREEZE.exists() or ORACLE_PLAN.exists():
        raise FileExistsError("实验冻结文件已存在；拒绝覆盖或重写冻结输入。")
    profile_rows = []
    oracle_rows = []
    for task_id, spec in TASK_SPECS.items():
        source = ROOT / spec["source"]
        profile_rows.append({"task_id": task_id, "project": spec["project"],
                             "contract": spec["contract"], "source": spec["source"],
                             "source_sha256": _sha(source),
                             "property": spec["property"],
                             "target_definition": spec["goal"]})
        oracle_rows.append({"task_id": task_id, "project": spec["project"],
                            "source_sha256": _sha(source),
                            "sequence": spec["oracle_steps"],
                            "getter_snapshot": spec["oracle_getters"],
                            "target_definition": spec["goal"],
                            "isolation": "仅由独立 Oracle 阶段读取；禁止传入 Agent、E2/E3/R/S 或种子语料"})
    historical = [HISTORICAL_WALLET, WALLET_ORACLE, PIGFOX_INPUT,
                  PIGFOX_COMPAT / "Properties.sol",
                  PIGFOX_COMPAT / "native-solc-source-manifest.json",
                  ROOT / "func/功能/状态反馈序列扩展.py",
                  ROOT / "func/功能/跨交易状态约束.py",
                  ROOT / "func/功能/属性分析适配器.py",
                  ROOT / "func/功能/属性种子上下文.py",
                  ROOT / "func/功能/种子验证.py",
                  ROOT / "deepseek/AgentA.py", ROOT / "deepseek/AgentB.py"]
    missing = [str(path) for path in historical if not path.is_file()]
    if missing:
        raise FileNotFoundError("冻结所需历史文件缺失：" + ", ".join(missing))
    wallet_driver = _load_phase31_driver()
    _, _, _, wallet_extras = wallet_driver._load_context()
    wallet_sequence = copy.deepcopy(wallet_extras["candidate"]["transactions"])
    pigfox_sequence = copy.deepcopy(_read_json(PIGFOX_INPUT)["sequence"])
    oracle_payload = {"schema_version": 1,
                      "created_before_formal_algorithm_run_utc": datetime.now(timezone.utc).isoformat(),
                      "manual_oracle_sequences": oracle_rows,
                      "historical_wallet_oracle": str(WALLET_ORACLE.relative_to(ROOT)),
                      "historical_pigfox_oracle": "Phase32-R 的 Anvil 逐笔 E1 状态记录；低依赖对照仅要求供给与余额和属性保持一致。"}
    _write_json(ORACLE_PLAN, oracle_payload)
    freeze_payload = {
        "schema_version": 1,
        "title": "V2 跨交易属性状态依赖能力专项审计",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "repository": "smart-contract-fuzz-v2",
        "branch": "main",
        "local_head": "dded14f7ad9fa7f05e999ff2319da946de79a7fb",
        "remote_main_head_verified_via_github_read_only_api": "dded14f7ad9fa7f05e999ff2319da946de79a7fb",
        "working_tree_before_audit": {
            "tracked_changes": 0,
            "preexisting_untracked": ["sol/真实项目/DODOCrossChain/", "sol/真实项目/Strata/",
                                       "sol/真实项目/VeryLiquidVaults/", "sol/真实项目/eBTC_BSM/"],
        },
        "scope": "最多五个主要场景；B 的改名变体属于同一任务；不修改核心算法；不提交、不推送、不启动下一阶段。",
        "scenario_contracts": profile_rows,
        "human_oracle_plan": {"path": str(ORACLE_PLAN.relative_to(ROOT)),
                              "sha256": _sha(ORACLE_PLAN),
                              "access_rule": "预先证明可达性/对照性质。Agent 运行入口不读取本文件或独立 Oracle 输出。"},
        "comparison_arms": {
            "E1": "仅复用冻结/一次性 Agent A/B 原始顺序与参数；B/C/D 各仅一次初始规划、最多一次 B 参数实例化，不重试。",
            "E2": "E1 加一次当前跨交易参数修复；保留全部交易步骤，记录是否实际修改及重放。",
            "E3": "E2 加当前状态反馈序列扩展。",
            "R": "相同 E1 初始候选与每场最多 24 次扩展执行预算的随机扩展。",
            "S": "相同 E1 初始候选与每场最多 24 次扩展执行预算的静态依赖扩展。",
        },
        "frozen_algorithm_parameters": {
            "head": "dded14f7ad9fa7f05e999ff2319da946de79a7fb",
            "max_sequence_length": 8,
            "candidate_execution_budget_per_extension_method": 24,
            "retained_prefixes": 4,
            "per_candidate_numeric_repair_limit": 1,
            "runtime_constraints": True,
            "extension_random_seed_base": 20261120,
            "accounts": SENDERS,
            "property_sender": PROPERTY_SENDER,
            "deployer": DEPLOYER,
            "contract_address": CONTRACT_ADDRESS,
            "initial_balance_wei_per_sender": "100000000000000000000",
            "anvil": {"version": "1.9.0-dev", "commit": "6056c5845d34205a83cf7108042adb137325c9df",
                      "chain_id": 1, "block_number": 4370000, "timestamp": 1524785992,
                      "hardfork": "shanghai", "gas_price_wei": 0, "block_gas_limit": 100000000},
            "echidna_seed_only": {"version": "2.3.2", "test_limit": 0,
                                  "confirmation_seed": 20261125,
                                  "no_fuzz_campaign": True},
            "solidity_compiler": {"version": "0.8.28", "path": str(SOLC)},
        },
        "agent_budget": {"model": "deepseek-flash", "thinking": "disabled",
                         "temperature": 0, "max_tokens_per_call": 4096,
                         "max_retries": 0, "planning_repairs": 0, "schema_repairs": 0,
                         "agent_a_max_candidates": 1, "agent_a_max_steps": 8,
                         "agent_a_calls": 1, "agent_b_calls": 1,
                         "api_calls_per_new_task_max": 2,
                         "token_budget_per_task": 400000, "wall_clock_budget_seconds_per_task": 600,
                         "cost": "记录 API 返回 usage 与本地冻结价目估算；不写入任何密钥"},
        "semantic_rename_transform": {
            "task": "BWorkflow only; no business semantics, property logic, ABI types, transition guards or oracle conditions change.",
            "function_map": TASK_SPECS["BWorkflow"]["rename_map"],
            "state_map": {"stage": "phase", "executionLimit": "quota",
                          "completedAmount": "appliedValue"},
            "property_map": {"echidna_workflow_respects_limit": "echidna_order_value_within_quota"},
            "Agent_calls_for_variant": 0,
        },
        "historical_input_sha256": {str(path.relative_to(ROOT)): _sha(path) for path in historical},
        "frozen_control_candidate_inputs": {
            "A_Wallet02Refund": {
                "source_report": str(HISTORICAL_WALLET.relative_to(ROOT)),
                "sequence": wallet_sequence,
                "sequence_sha256": hashlib.sha256(json.dumps(
                    wallet_sequence, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest(),
                "classification": "Phase31的冻结原始P1输入；不能使用E3胜出序列替代"},
            "E_PigfoxRWASupplySum": {
                "source_report": str(PIGFOX_INPUT.relative_to(ROOT)),
                "sequence": pigfox_sequence,
                "sequence_sha256": hashlib.sha256(json.dumps(
                    pigfox_sequence, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest(),
                "classification": "Phase32-R冻结E1输入；所有组共用此初始序列"},
        },
        "execution_code_sha256": {str(path.relative_to(ROOT)): _sha(path) for path in [
            Path(__file__).resolve(),
            ROOT / "func/测试过程/SCFuzzBench公开项目接入/Phase32有限扩展与对照.py",
            ROOT / "func/测试过程/SCFuzzBench公开项目接入/Phase31状态反馈序列扩展.py",
            ROOT / "func/测试过程/SCFuzzBench公开项目接入/Phase32R正式实验.py",
            ROOT / "deepseek/实验过程/运行Agent种子流程.py",
            ROOT / "deepseek/deepseek接口.py",
        ]},
        "core_algorithm_sha256": {str(path.relative_to(ROOT)): _sha(path) for path in [
            ROOT / "func/功能/属性分析适配器.py", ROOT / "func/功能/属性种子上下文.py",
            ROOT / "func/功能/跨交易状态约束.py", ROOT / "func/功能/状态反馈序列扩展.py",
            ROOT / "func/功能/种子验证.py", ROOT / "deepseek/AgentA.py", ROOT / "deepseek/AgentB.py"]},
        "historical_positive_and_negative_controls": {
            "A_Wallet02Refund": {"input": str(HISTORICAL_WALLET.relative_to(ROOT)),
                                 "oracle": str(WALLET_ORACLE.relative_to(ROOT)),
                                 "initial_candidate_source": "Phase30B frozen P1 source-context planner; no new model call"},
            "E_PigfoxRWASupplySum": {"input": str(PIGFOX_INPUT.relative_to(ROOT)),
                                     "compatibility_harness": str((PIGFOX_COMPAT / "Properties.sol").relative_to(ROOT)),
                                     "oracle": "Phase32-R E1 Anvil state trajectory; property true with totalSupply equal to holder-balance sum",
                                     "note": "same read-only Harness adaptation for all methods; not an unmodified upstream Harness run"},
        },
        "stop_rules": ["最多五个主要场景。", "B/C/D 每类只调用一次 A/B 初始规划。",
                       "不修改算法、真实项目业务逻辑、冻结合约、属性或预算。",
                       "编译/部署/Harness 单类问题最多一次有明确依据的通用环境修复。",
                       "未执行场景标记未验证，不计为成功或失败。"],
    }
    _write_json(FREEZE, freeze_payload)
    print(json.dumps({"freeze": str(FREEZE.relative_to(ROOT)),
                      "freeze_sha256": _sha(FREEZE),
                      "oracle_plan_sha256": _sha(ORACLE_PLAN),
                      "scenario_input_count": len(profile_rows)}, ensure_ascii=False))


def _load_phase31_driver():
    path = ROOT / "func/测试过程/SCFuzzBench公开项目接入/Phase31状态反馈序列扩展.py"
    spec = importlib.util.spec_from_file_location("audit_phase31_wallet", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法导入既有 Phase31 Wallet 驱动")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_phase32r_driver():
    path = ROOT / "func/测试过程/SCFuzzBench公开项目接入/Phase32R正式实验.py"
    spec = importlib.util.spec_from_file_location("audit_phase32r_pigfox", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法导入既有 Phase32-R 驱动")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _register_profile(task_id: str, spec: dict[str, Any], report: Path,
                      artifact: Path) -> None:
    from 属性种子上下文 import PROJECTS

    source_path = ROOT / spec["source"]
    source_root = source_path.parent
    PROJECTS[spec["project"]] = {
        "report": str(report.relative_to(ROOT)),
        "artifact": str(artifact.relative_to(ROOT)),
        "source_root": str(source_root.relative_to(ROOT)),
        "contract": spec["contract"],
        "target": str(source_path.relative_to(ROOT)),
        "fuzzer_target": str(source_path),
        "solc_version": "0.8.28", "solc": str(SOLC),
        "solc_args": "--optimize --optimize-runs 200 --evm-version shanghai",
        "foundry": False,
        "constructor_args": [],
        "deployment": {"mode": "constructor", "constructor_args": [],
                       "deployer": DEPLOYER, "contract_address": CONTRACT_ADDRESS,
                       "address_derivation": "CREATE(deployer, nonce=0)"},
        "execution": {"chain_id": 1, "deployment_timestamp": 1524785992,
                      "deployment_block_number": 4370000, "base_fee_per_gas": 0,
                      "gas_price": 0, "block_gas_limit": 100000000,
                      "initial_balance": 100000000000000000000,
                      "max_transaction_gas": 12500000, "hardfork": "shanghai"},
        "property": {"mode": "property", "prefix": "echidna_",
                     "sender": PROPERTY_SENDER, "target_property": spec["property"] + "()"},
        "senders": list(SENDERS),
        "echidna": {"prefix": "echidna_", "workers": 1,
                    "call_sequence_length": 8, "stop_on_fail": False,
                    "disable_slither": True},
    }


def _compile_artifact(task_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    source = ROOT / spec["source"]
    out = RUN_ROOT / "01-编译与静态分析" / task_id
    out.mkdir(parents=True, exist_ok=True)
    artifact_path = out / "编译产物.json"
    command = [str(SOLC), "--combined-json", "abi,bin", str(source)]
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (out / "solc.log").write_text(result.stdout, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"{task_id} solc compile failed: {result.stdout[-1200:]}")
    payload = json.loads(result.stdout[result.stdout.find("{"):])
    contract_data = next((item for key, item in payload.get("contracts", {}).items()
                          if key.split(":")[-1] == spec["contract"]), None)
    if contract_data is None:
        raise RuntimeError(f"{task_id} compiled contract {spec['contract']} not found")
    all_abis = {key.split(":")[-1]: value["abi"]
                for key, value in payload.get("contracts", {}).items()}
    artifact = {"compiler": {"name": "solc", "version": "0.8.28"},
                "contractName": spec["contract"], "abi": contract_data["abi"],
                "bytecode": "0x" + contract_data["bin"],
                "contract_abis": all_abis}
    _write_json(artifact_path, artifact)
    summary = {"task_id": task_id, "command": command,
               "exit_code": result.returncode,
               "source_sha256": _sha(source), "artifact_sha256": _sha(artifact_path),
               "elapsed_seconds": round(time.monotonic() - started, 6),
               "contract": spec["contract"], "abi_entries": len(contract_data["abi"]),
               "bytecode_bytes": len(contract_data["bin"]) // 2}
    _write_json(out / "compile-summary.json", summary)
    return {"artifact_path": artifact_path, "artifact": artifact, "summary": summary}


def _analyze_task(task_id: str, spec: dict[str, Any], artifact_path: Path) -> dict[str, Any]:
    source = ROOT / spec["source"]
    out = RUN_ROOT / "01-编译与静态分析" / task_id
    report_path = out / "属性分析.json"
    command = [sys.executable, str(ROOT / "func/功能/属性分析适配器.py"),
               str(source), "--contract", spec["contract"],
               "--project-root", str(source.parent), "--solc", str(SOLC),
               "--output", str(report_path)]
    result = subprocess.run(command, cwd=ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (out / "slither-adapter.log").write_text(result.stdout, encoding="utf-8")
    if result.returncode != 0 or not report_path.is_file():
        raise RuntimeError(f"{task_id} Slither adapter failed: {result.stdout[-1800:]}")
    report = _read_json(report_path)
    properties = report.get("properties", [])
    if len(properties) != 1:
        raise RuntimeError(f"{task_id} expected one explicit property, got {len(properties)}")
    prop = properties[0]
    _register_profile(task_id, spec, report_path, artifact_path)
    spec["runtime_property_id"] = prop["property_id"]
    spec["report_path"] = report_path
    spec["artifact_path"] = artifact_path
    return {"task_id": task_id, "report_path": str(report_path.relative_to(ROOT)),
            "report_sha256": _sha(report_path),
            "property_id": prop["property_id"], "property": prop["property"],
            "property_kind": prop.get("property_kind"),
            "analysis_status": prop.get("analysis_status"),
            "dependency_status": prop.get("dependency_status"),
            "read_states": prop.get("read_states", []),
            "candidate_actions": [item.get("abi_signature")
                                  for item in prop.get("candidate_actions", [])],
            "cross_contract_observations": prop.get("cross_contract", {}).get("observations", []),
            "cross_contract_candidate_actions": prop.get("cross_contract", {}).get("candidate_actions", []),
            "static_unknowns": prop.get("unknowns", [])}


def _getter_values(contract, getter_specs: list[dict[str, Any]], sender: str) -> list[dict[str, Any]]:
    rows = []
    for row in getter_specs:
        try:
            value = contract.get_function_by_signature(row["function"])(
                *row.get("arguments", [])).call({"from": sender})
            rows.append({**row, "status": "observed", "value": value})
        except Exception as exc:
            rows.append({**row, "status": "call_error",
                         "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
    return rows


def _run_oracle(task_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    from 种子验证 import AnvilSession, _decode_revert_reason, _trace_effects, read_json
    from 属性种子上下文 import PROJECTS
    project = spec["project"]
    config = PROJECTS[project]
    artifact = read_json(config["artifact"])
    out = RUN_ROOT / "02-独立Oracle" / f"{task_id}-独立Oracle.json"
    session = AnvilSession(project=project)
    started = time.monotonic()
    steps = []
    try:
        session.__enter__()
        factory = session.web3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
        deployment_hash = factory.constructor().transact({"from": DEPLOYER,
                                                          "gas": session.gas_limit,
                                                          "gasPrice": 0})
        deployment_receipt = session.web3.eth.wait_for_transaction_receipt(deployment_hash, timeout=60)
        if deployment_receipt.status != 1 or deployment_receipt.contractAddress.lower() != CONTRACT_ADDRESS.lower():
            raise RuntimeError("Oracle harness deployment failed or address mismatched")
        contract = session.web3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS),
                                             abi=artifact["abi"])
        prop_signature = spec["property"] + "()"
        initial_property = bool(contract.get_function_by_signature(prop_signature)().call(
            {"from": PROPERTY_SENDER}))
        initial_getters = _getter_values(contract, spec["oracle_getters"], PROPERTY_SENDER)
        for index, raw in enumerate(spec["oracle_steps"], start=1):
            args = copy.deepcopy(raw["arguments"])
            fn = contract.get_function_by_signature(raw["function"])(*args)
            tx_hash = fn.transact({"from": Web3.to_checksum_address(raw["sender"]),
                                   "value": int(raw.get("value_wei", 0)),
                                   "gas": session.max_transaction_gas, "gasPrice": 0})
            receipt = session.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            trace = _trace_effects(session, tx_hash)
            prop_value = None
            if receipt.status == 1:
                prop_value = bool(contract.get_function_by_signature(prop_signature)().call(
                    {"from": PROPERTY_SENDER}))
            steps.append({"index": index, "function": raw["function"],
                          "arguments": args, "sender": raw["sender"],
                          "value_wei": str(raw.get("value_wei", 0)),
                          "receipt_status": int(receipt.status),
                          "transaction_hash": tx_hash.hex(), "gas_used": int(receipt.gasUsed),
                          "revert_reason": _decode_revert_reason(trace.get("top_level_output")),
                          "trace": trace, "target_property": prop_value,
                          "getter_snapshot": _getter_values(contract, spec["oracle_getters"], PROPERTY_SENDER)
                          if receipt.status == 1 else []})
            if receipt.status != 1:
                break
        final_property = steps[-1].get("target_property") if steps else initial_property
        final_getters = steps[-1].get("getter_snapshot") if steps else initial_getters
        target = _oracle_goal_reached(spec, final_getters)
        result = {"task_id": task_id, "project": project,
                  "status": "oracle_reached" if target else "oracle_not_reached",
                  "deployment": {"status": int(deployment_receipt.status),
                                 "transaction_hash": deployment_hash.hex(),
                                 "address": deployment_receipt.contractAddress},
                  "initial_property": initial_property, "initial_getters": initial_getters,
                  "steps": steps, "final_property": final_property,
                  "final_getters": final_getters,
                  "target_goal": spec["goal"], "target_reached": target,
                  "oracle_sequence_sha256": hashlib.sha256(json.dumps(
                      spec["oracle_steps"], ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode()).hexdigest(),
                  "elapsed_seconds": round(time.monotonic() - started, 6),
                  "isolation": "Oracle only; no steps or output passed to Agent A/B or extension methods"}
    except Exception as exc:
        result = {"task_id": task_id, "project": project, "status": "oracle_blocked",
                  "error": f"{type(exc).__name__}: {str(exc)[:1200]}",
                  "steps": steps, "elapsed_seconds": round(time.monotonic() - started, 6)}
    finally:
        session.__exit__(None, None, None)
    _write_json(out, result)
    return result


def _oracle_goal_reached(spec: dict[str, Any], getter_rows: list[dict[str, Any]]) -> bool:
    values = {row["function"] + ":" + json.dumps(row.get("arguments", []), sort_keys=True): row.get("value")
              for row in getter_rows if row.get("status") == "observed"}
    goal = spec["goal"]
    kind = goal["kind"]
    if kind == "workflow_stage":
        return (values.get(goal["stage_getter"] + ":[]") == goal["stage"] and
                values.get(goal["completed_getter"] + ":[]", 0) >= goal["completed_min"])
    if kind == "delegated_execution":
        owner = json.dumps([goal["owner"]], sort_keys=True)
        operator = values.get(goal["authorization_getter"] + ":" + owner)
        executed = values.get(goal["executed_getter"] + ":" + owner, 0)
        deposited = values.get(goal["deposit_getter"] + ":" + owner, 0)
        return deposited > 0 and operator and operator.lower() == goal["operator"].lower() and executed >= goal["amount"]
    if kind == "delegated_spend":
        pair = json.dumps([goal["owner"], goal["spender"]], sort_keys=True)
        spent = values.get(goal["spent_getter"] + ":" + pair, 0)
        granted = values.get(goal["grant_getter"] + ":" + pair, 0)
        allowance = values.get(goal["allowance_getter"] + ":" + pair, 0)
        balance = values.get(goal["balance_getter"] + ":" + json.dumps([goal["owner"]], sort_keys=True), 0)
        return granted >= goal["amount"] and spent >= goal["amount"] and allowance < granted and balance > 0
    return False


def preflight() -> None:
    if not FREEZE.is_file():
        raise FileNotFoundError("先运行 --freeze-only 并检查冻结文件，再开始预检。")
    freeze_payload = _read_json(FREEZE)
    if _sha(ORACLE_PLAN) != freeze_payload["human_oracle_plan"]["sha256"]:
        raise RuntimeError("独立 Oracle 计划哈希与冻结记录不一致")
    for task_id, spec in TASK_SPECS.items():
        compiled = _compile_artifact(task_id, spec)
        _register_profile(task_id, spec, RUN_ROOT / "01-编译与静态分析" / task_id / "属性分析.json",
                          compiled["artifact_path"])
    analysis_rows = []
    for task_id, spec in TASK_SPECS.items():
        report_path = RUN_ROOT / "01-编译与静态分析" / task_id / "属性分析.json"
        artifact_path = RUN_ROOT / "01-编译与静态分析" / task_id / "编译产物.json"
        row = _analyze_task(task_id, spec, artifact_path)
        analysis_rows.append(row)
    _write_json(RUN_ROOT / "01-编译与静态分析" / "静态分析汇总.json", analysis_rows)
    oracle_rows = [_run_oracle(task_id, spec) for task_id, spec in TASK_SPECS.items()]
    historic = _verify_historical_oracles()
    preflight_result = {"status": "complete", "frozen_inputs_unchanged": all(
        _sha(ROOT / item["source"]) == item["source_sha256"]
        for item in freeze_payload["scenario_contracts"]),
        "static_analysis": analysis_rows, "oracle": oracle_rows,
        "historical_oracle_evidence": historic,
        "agent_may_run": all(item.get("status") == "oracle_reached" for item in oracle_rows)
                         and all(item.get("status") == "verified" for item in historic)}
    _write_json(RUN_ROOT / "02-预检总汇.json", preflight_result)
    print(json.dumps({"status": preflight_result["status"],
                      "oracle_status": {row["task_id"]: row["status"] for row in oracle_rows},
                      "agent_may_run": preflight_result["agent_may_run"],
                      "summary": str((RUN_ROOT / "02-预检总汇.json").relative_to(ROOT))}, ensure_ascii=False))


def _verify_historical_oracles() -> list[dict[str, Any]]:
    rows = []
    wallet = _read_json(WALLET_ORACLE)
    wallet_anvil = wallet.get("anvil", {})
    rows.append({"scenario": "A_Wallet02Refund", "status": "verified" if
                 wallet_anvil.get("target_state_reached") is True and
                 wallet_anvil.get("final_property_value") is False and
                 len(wallet_anvil.get("transaction_rows", [])) > 0 else "unverified",
                 "path": str(WALLET_ORACLE.relative_to(ROOT)), "sha256": _sha(WALLET_ORACLE),
                 "final_property_value": wallet_anvil.get("final_property_value"),
                 "oracle_target_state_reached": wallet_anvil.get("target_state_reached"),
                 "source_report": "docs/31_目标可达性与多交易规划修复.md"})
    pigfox_validation = _read_json(PIGFOX_COMPAT.parent / "Observer/validation-summary.json")
    matrix = _read_json(PIGFOX_COMPAT.parent / "Echidna/matrix.json")
    e1 = _read_json(PIGFOX_INPUT)
    e1_sequence = e1.get("sequence", [])
    rows.append({"scenario": "E_PigfoxRWASupplySum",
                 "status": "verified" if pigfox_validation.get("replay_status") == "executable" and
                 pigfox_validation.get("initial_target_property") is True and
                 pigfox_validation.get("final_target_property") is True and
                 len(pigfox_validation.get("property_related_getter_changes", [])) >= 2 and
                 len(e1_sequence) > 0 and matrix.get("status") == "completed" else "unverified",
                 "input": str(PIGFOX_INPUT.relative_to(ROOT)), "input_sha256": _sha(PIGFOX_INPUT),
                 "observer": str((PIGFOX_COMPAT.parent / "Observer/validation-summary.json").relative_to(ROOT)),
                 "observer_sha256": _sha(PIGFOX_COMPAT.parent / "Observer/validation-summary.json"),
                 "seed_only_matrix_sha256": _sha(PIGFOX_COMPAT.parent / "Echidna/matrix.json"),
                 "note": "Phase32-R Anvil 逐笔状态已证明供给与持有人余额同增且属性保持真；本轮将它定义为低依赖无增益对照。"})
    return rows


def _capture_call(original, task_id: str, agent: str, capture_root: Path):
    def wrapped(**kwargs):
        user = kwargs.get("user", "")
        tag = str(kwargs.get("tag", agent))
        path = capture_root / f"{agent}-{task_id}-{tag.rsplit('_', 1)[-1]}.json"
        safe = {"agent": agent, "task_id": task_id, "tag": tag,
                "system": kwargs.get("system"), "user": user,
                "model": kwargs.get("model", "deepseek-flash"),
                "thinking": kwargs.get("thinking", "disabled"),
                "max_tokens": kwargs.get("max_tokens", 4096),
                "temperature": 0, "max_retries": kwargs.get("max_retries", 0),
                "prompt_sha256": hashlib.sha256(user.encode("utf-8")).hexdigest(),
                "oracle_plan_sha256": _sha(ORACLE_PLAN),
                "oracle_plan_included": False}
        safe["oracle_plan_included"] = safe["oracle_plan_sha256"] in user
        if safe["oracle_plan_included"]:
            raise RuntimeError("检测到独立 Oracle 计划哈希进入 Agent 输入；已阻止模型调用")
        _write_json(path, safe)
        return original(**kwargs)
    return wrapped


def _agent_initial_candidate(task_id: str, spec: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    from deepseek接口 import CallBudget
    from 属性种子上下文 import PROJECTS, load_project_context
    pipeline_path = ROOT / "deepseek/实验过程/运行Agent种子流程.py"
    pipeline_spec = importlib.util.spec_from_file_location("audit_agent_pipeline", pipeline_path)
    if pipeline_spec is None or pipeline_spec.loader is None:
        raise RuntimeError("无法导入现有 Agent A/B 逐属性流程")
    pipeline = importlib.util.module_from_spec(pipeline_spec)
    pipeline_spec.loader.exec_module(pipeline)
    # Capture exact, secret-free prompt payloads without changing Agent A/B logic.
    agent_a_mod = sys.modules.get("AgentA")
    if agent_a_mod is None:
        import AgentA as agent_a_mod
    agent_b_mod = sys.modules.get("AgentB")
    if agent_b_mod is None:
        import AgentB as agent_b_mod
    capture_root = RUN_ROOT / "03-Agent输入与输出" / task_id
    api_log = capture_root / "API调用.jsonl"
    original_a = agent_a_mod.call_json
    original_b = agent_b_mod.call_json
    agent_a_mod.call_json = _capture_call(original_a, task_id, "AgentA", capture_root)
    agent_b_mod.call_json = _capture_call(original_b, task_id, "AgentB", capture_root)
    budget = CallBudget(400000, deadline_monotonic=time.monotonic() + 600)
    call_options = {"budget": budget, "log_path": api_log,
                    "max_retries": 0, "timeout": 120,
                    "model": "deepseek-flash", "thinking": "disabled"}
    context = load_project_context(spec["project"], [spec["runtime_property_id"]])
    prop = context["properties"][0]
    project_config = PROJECTS[spec["project"]]
    from 种子验证 import AnvilSession, inspect_initial_state, replay_seed

    deployment_state: dict[str, Any]
    try:
        with AnvilSession(project=spec["project"]) as session:
            deployment_state = inspect_initial_state(spec["project"], prop, session=session)
    except Exception as exc:
        deployment_state = {"status": "unavailable", "error": f"{type(exc).__name__}: {str(exc)[:800]}"}
    role_senders = [item["address"] for item in deployment_state.get("role_addresses", [])]
    sender_pool = list(dict.fromkeys([*project_config.get("senders", SENDERS), *role_senders]))
    context = {**context, "deployment_state": deployment_state,
               "sender_pool": sender_pool,
               "agent_environment": {"chain_id": 1, "initial_timestamp": 1524785992,
                                     "initial_block_number": 4370000,
                                     "evm_revision": "shanghai",
                                     "harness_address": CONTRACT_ADDRESS,
                                     "property_sender": PROPERTY_SENDER,
                                     "gas_price_wei": 0,
                                     "gas_limit_per_transaction": 12500000}}
    property_id = spec["runtime_property_id"]
    candidates, a_events, planning = pipeline._agent_a_for_property(
        context, property_id, max_candidates=1, max_steps=8,
        planning_repairs=0, tag=f"AgentA_{spec['project']}_{property_id}",
        call_options=call_options)
    result: dict[str, Any] = {"task_id": task_id, "project": spec["project"],
                              "model": "deepseek-flash", "agent_a_events": a_events,
                              "planning": planning, "agent_b_events": [],
                              "status": "agent_a_no_candidate", "candidate": None,
                              "initial_replay": None, "api_log": str(api_log.relative_to(ROOT)),
                              "token_budget_spent": budget.spent_tokens,
                              "api_call_count": budget.calls}
    candidate_out = None
    if candidates:
        raw = candidates[0]
        candidate = pipeline._candidate_context(raw, context)
        candidate["candidate_id"] = f"{property_id[:12]}-01-{raw['candidate_id']}"
        concrete, b_events, error = pipeline._agent_b_call(
            context, candidate, feedback=None, first_attempt=1,
            schema_repairs=0, call_options=call_options)
        result["agent_b_events"] = b_events
        result["agent_b_error"] = error
        if concrete:
            candidate_out = {**concrete, "project": spec["project"],
                             "property": prop["property"], "context": context}
            replay = replay_seed(spec["project"], candidate_out,
                                 concrete["transactions"], runtime_constraints=False)
            result["initial_replay"] = replay
            result["status"] = replay.get("replay_status", "replay_failed")
            result["candidate"] = {key: value for key, value in concrete.items()
                                    if key != "context"}
            result["agent_a_candidate"] = raw
        else:
            result["status"] = "agent_b_no_concrete_seed"
    result["token_budget_spent"] = budget.spent_tokens
    result["api_call_count"] = budget.calls
    result["api_usage"] = pipeline._api_summary(api_log)
    result_path = capture_root / "AgentAB初始种子.json"
    _write_json(result_path, result)
    agent_a_mod.call_json = original_a
    agent_b_mod.call_json = original_b
    if candidate_out:
        candidate_out["context"] = context
    return candidate_out, result


def _historical_wallet_input():
    from 属性种子上下文 import load_project_context
    wallet_driver = _load_phase31_driver()
    config, context, abi_by_signature, extras = wallet_driver._load_context()
    candidate = extras["candidate"]
    candidate["context"] = context
    spec = {"task_id": "A_Wallet02Refund", "project": "Wallet02Refund"}
    sequence = copy.deepcopy(candidate["transactions"])
    return spec, context, extras["property"], candidate, sequence, {
        "source": str(HISTORICAL_WALLET.relative_to(ROOT)),
        "source_sha256": _sha(HISTORICAL_WALLET),
        "agent_calls_this_audit": 0,
        "prior_agent_cost_source": str((ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Wallet02Refund/06-agent-v2/API调用.jsonl").relative_to(ROOT)),
    }


def _historical_pigfox_input(phase32r):
    from 属性种子上下文 import PROJECTS, load_project_context, read_json
    phase32r.configure_compatibility_artifact()
    source = read_json(PIGFOX_INPUT)
    project = "Phase32PigfoxRWADemo"
    property_id = "2e998090c7de1e70f195"
    context = load_project_context(project, [property_id])
    prop = context["properties"][0]
    context = {**context, "properties": [prop],
               "sender_pool": list(PROJECTS[project].get("senders") or SENDERS)}
    concrete = {"project": project, "property_id": property_id,
                "candidate_id": source["candidate_id"],
                "transactions": copy.deepcopy(source["sequence"])}
    candidate = {**concrete, "property": prop["property"], "context": context}
    return {"task_id": "E_PigfoxRWASupplySum", "project": project}, context, prop, candidate, copy.deepcopy(source["sequence"]), {
        "source": str(PIGFOX_INPUT.relative_to(ROOT)), "source_sha256": _sha(PIGFOX_INPUT),
        "agent_calls_this_audit": 0,
        "prior_agent_cost_source": str((PIGFOX_INPUT.parent.parent / "seed-preparation-costs.json").relative_to(ROOT)),
    }


def _target_state(replay: dict[str, Any], goal: dict[str, Any], prop: dict[str, Any]) -> dict[str, Any]:
    initial_rows = replay.get("initial_predicate_getters", [])
    tx_rows = replay.get("transactions", [])
    final_rows = tx_rows[-1].get("predicate_getter_values", []) if tx_rows else initial_rows
    values: dict[tuple[str, str], Any] = {}
    for row in final_rows:
        if row.get("status") == "observed":
            values[(str(row.get("signature")), json.dumps(row.get("arguments", []), sort_keys=True))] = row.get("value")
    def get(signature: str, args: list[Any] | None = None, default: Any = None):
        return values.get((signature, json.dumps(args or [], sort_keys=True)), default)
    kind = goal.get("kind")
    if kind == "workflow_stage":
        state_values = {"stage": get(goal["stage_getter"]),
                        "completed": get(goal["completed_getter"], default=0)}
        reached = state_values["stage"] == goal["stage"] and state_values["completed"] is not None and state_values["completed"] >= goal["completed_min"]
    elif kind == "delegated_execution":
        owner = goal["owner"]
        state_values = {"deposit": get(goal["deposit_getter"], [owner], 0),
                        "available": get(goal["available_getter"], [owner], 0),
                        "authorized_operator": get(goal["authorization_getter"], [owner]),
                        "executed": get(goal["executed_getter"], [owner], 0)}
        operator = state_values["authorized_operator"]
        reached = bool(state_values["deposit"] and state_values["executed"] >= goal["amount"] and
                       isinstance(operator, str) and operator.lower() == goal["operator"].lower())
    elif kind == "delegated_spend":
        owner, spender = goal["owner"], goal["spender"]
        pair = [owner, spender]
        state_values = {"owner_balance": get(goal["balance_getter"], [owner], 0),
                        "spender_balance": get(goal["balance_getter"], [spender], 0),
                        "allowance": get(goal["allowance_getter"], pair, 0),
                        "total_granted": get(goal["grant_getter"], pair, 0),
                        "delegated_spent": get(goal["spent_getter"], pair, 0),
                        "total_supply": get(goal["supply_getter"], default=0)}
        reached = (state_values["total_granted"] >= goal["amount"] and
                   state_values["delegated_spent"] >= goal["amount"] and
                   state_values["allowance"] < state_values["total_granted"])
    elif goal.get("kind") == "rwa_supply_sum":
        state_values = {row.get("signature") + ":" + json.dumps(row.get("arguments", []), sort_keys=True): row.get("value")
                        for row in final_rows if row.get("status") == "observed"}
        reached = bool((replay.get("target_property_state") or {}).get("property_related_state_changed"))
    elif goal.get("kind") == "wallet_counterexample":
        state_values = {"target_property": replay.get("transactions", [{}])[-1].get("target_property") if tx_rows else None}
        reached = state_values["target_property"] is False
    else:
        state_values = {}
        reached = False
    return {"goal_kind": kind, "reached": bool(reached),
            "goal_state_values": state_values,
            "reason": ("预先定义的关键持久状态全部成立" if reached else
                       "关键状态未满足；按逐笔 getter 与交易 trace 定位缺口"),
            "property_value": (tx_rows[-1].get("target_property") if tx_rows else
                               next(iter(replay.get("initial_property_values", {}).values()), None)),
            "property_related_state_changed": bool((replay.get("target_property_state") or {}).get(
                "property_related_state_changed")),
            "replay_status": replay.get("replay_status"),
            "getter_observation_incomplete": (replay.get("target_property_state") or {}).get(
                "status") == "property_state_unobservable"}


def _translate_variant(sequence: list[dict[str, Any]], mapping: dict[str, str]) -> list[dict[str, Any]]:
    result = copy.deepcopy(sequence)
    for tx in result:
        tx["function"] = mapping.get(tx["function"], tx["function"])
    return result


def _run_extension(task_id: str, project: str, prop: dict[str, Any],
                   candidate: dict[str, Any], sequence: list[dict[str, Any]],
                   metadata: dict[str, Any]) -> dict[str, Any]:
    from 属性种子上下文 import PROJECTS
    from 种子验证 import replay_seed
    import Phase32有限扩展与对照 as extension_driver

    artifact_path = Path(PROJECTS[project]["artifact"])
    if not artifact_path.is_absolute():
        artifact_path = ROOT / artifact_path
    artifact = _read_json(artifact_path)
    abi_by_signature = {
        entry["name"] + "(" + ",".join(row["type"] for row in entry.get("inputs", [])) + ")": entry
        for entry in artifact["abi"] if entry.get("type") == "function"}
    senders = list(PROJECTS[project].get("senders") or SENDERS)
    out = RUN_ROOT / "04-Anvil对照" / task_id
    out.mkdir(parents=True, exist_ok=True)
    e1 = replay_seed(project, candidate, copy.deepcopy(sequence), runtime_constraints=False)
    _write_json(out / "E1-AgentAB-原始候选.json", {
        "task_id": task_id, "sequence": sequence, "sequence_sha256": hashlib.sha256(
            json.dumps(sequence, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")).encode()).hexdigest(),
        "replay": e1, "target_state": _target_state(e1, metadata["goal"], prop)})
    e1base = _target_state(e1, metadata["goal"], prop)
    # E2 has its own clean deployment; E3/R/S each create separate sessions in _expand.
    with extension_driver.AnvilSession(project=project) as session:
        repaired, e2, repair, repair_count = extension_driver._replay_candidate(
            project, candidate, copy.deepcopy(sequence), session)
    e2base = _target_state(e2, metadata["goal"], prop)
    _write_json(out / "E2-参数修复.json", {
        "task_id": task_id, "sequence": repaired,
        "sequence_sha256": hashlib.sha256(json.dumps(repaired, ensure_ascii=False,
                                                     sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "parameter_repair": repair, "parameter_repair_replays": repair_count,
        "replay": e2, "target_state": e2base,
        "repair_effective": bool(repair and e2.get("replay_status") == "executable" and
                                  e2base["reached"] and not e1base["reached"])})
    expansion_root = out / "extensions"
    expansion = extension_driver._expand(project, candidate, prop, abi_by_signature,
                                        copy.deepcopy(sequence), senders, expansion_root)
    method_summaries = {}
    for mode, row in expansion["modes"].items():
        group = row["group"]
        candidates = []
        for item in row.get("records", []):
            if item.get("candidate_no") == 0:
                continue
            replay = item.get("replay", {})
            target = _target_state(replay, metadata["goal"], prop)
            candidates.append({"candidate_no": item.get("candidate_no"),
                               "sequence": item.get("sequence"),
                               "sequence_fingerprint": item.get("sequence_fingerprint"),
                               "operator": item.get("origin"),
                               "proposal_reason": item.get("proposal_reason"),
                               "proposal_evidence": item.get("proposal_evidence"),
                               "parameter_repair": item.get("parameter_repair"),
                               "replay_status": replay.get("replay_status"),
                               "transaction_outcomes": [{key: tx.get(key) for key in (
                                   "index", "function", "sender", "value_wei", "status",
                                   "execution_class", "internal_errors", "changed_predicate_getters",
                                   "balance_changes", "changed_storage_slot_count")}
                                   for tx in replay.get("transactions", [])],
                               "target_state": target,
                               "extension_record": item})
        method_summaries[group] = {
            "mode": mode, "group": group,
            "status": row.get("status"),
            "candidate_execution_budget": row.get("candidate_execution_budget"),
            "candidate_executions": row.get("candidate_executions"),
            "parameter_repair_replays": row.get("parameter_repair_replays"),
            "total_anvil_replays": row.get("total_anvil_replays"),
            "elapsed_seconds": row.get("elapsed_seconds"),
            "base_sequence": row.get("base_sequence"),
            "base_parameter_repair": row.get("base_parameter_repair"),
            "candidates": candidates,
            "raw_log": str((expansion_root / f"{group}-扩展回放.json").relative_to(ROOT)),
        }
        _write_json(out / f"{group}-候选状态汇总.json", method_summaries[group])
    summary = {"task_id": task_id, "project": project,
               "initial_sequence": sequence,
               "initial_sequence_fingerprint": hashlib.sha256(json.dumps(
                   sequence, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode()).hexdigest(),
               "E1": {"replay_status": e1.get("replay_status"), "target_state": e1base,
                      "sequence": sequence},
               "E2": {"replay_status": e2.get("replay_status"), "target_state": e2base,
                      "parameter_repair": repair, "sequence": repaired},
               "E3_R_S": method_summaries,
               "method_comparison": _method_decision(e1base, e2base, method_summaries,
                                                       metadata["goal"], repaired),
               "metadata": metadata,
               "human_oracle_read_by_expansion": False}
    _write_json(out / "方法对照总汇.json", summary)
    return {"summary": summary, "candidate": candidate, "context": candidate["context"],
            "property": prop, "method_summaries": method_summaries,
            "E1_replay": e1, "E2_replay": e2}


def _method_decision(e1: dict[str, Any], e2: dict[str, Any], methods: dict[str, Any],
                     goal: dict[str, Any], e2_sequence: list[dict[str, Any]]) -> dict[str, Any]:
    e2_only = bool(e2.get("reached") and not e1.get("reached"))
    result = {"agent_a_or_b_reached_goal": bool(e1.get("reached")),
              "parameter_repair_reached_goal": e2_only,
              "parameter_repair_changed_sequence": bool(e2_only or
                    any(row.get("parameter_repair") for row in methods.values())),
              "goal_kind": goal.get("kind"), "extension_attribution": {}}
    for group, method in methods.items():
        reached = next((row for row in method.get("candidates", [])
                        if row.get("target_state", {}).get("reached")), None)
        candidates = method.get("candidates", [])
        repeated_count = sum(row.get("operator") == "state_supported_repetition"
                             for row in candidates)
        newly_reached = bool(reached and not e2.get("reached"))
        reached_sequence = reached.get("sequence", []) if reached else []
        inserted_calls = max(0, len(reached_sequence) - len(e2_sequence)) if reached else 0
        reached_by_repetition = bool(reached and
                                     reached.get("operator") == "state_supported_repetition")
        result["extension_attribution"][group] = {
            "reached_frozen_goal": bool(reached),
            "newly_reached_after_E2": newly_reached,
            "first_goal_candidate_no": reached.get("candidate_no") if reached else None,
            "first_goal_operator": reached.get("operator") if reached else None,
            "reached_by_repetition": reached_by_repetition,
            "candidate_added_transaction_count": inserted_calls,
            "candidate_added_transaction_step": inserted_calls > 0,
            "repetition_candidate_count": repeated_count,
            "only_repetition_observed": bool(candidates and repeated_count == len(candidates)),
            "candidate_count": method.get("candidate_executions"),
            "contribution": ("new_transaction_steps_reached_frozen_goal" if newly_reached else
                             "base_candidate_already_reached_goal" if reached else
                             "repetition_without_goal_completion" if repeated_count else
                             "no_goal_completion")}
        if newly_reached and reached_by_repetition:
            result["extension_attribution"][group]["contribution"] = \
                "repeated_existing_transaction_reached_frozen_goal"
        elif newly_reached and inserted_calls == 0:
            result["extension_attribution"][group]["contribution"] = \
                "modified_or_reordered_existing_steps_reached_frozen_goal"
    return result


def _run_echidna_confirmation(task_id: str, group: str, candidate: dict[str, Any],
                              prop: dict[str, Any], sequence: list[dict[str, Any]],
                              replay: dict[str, Any], project: str) -> dict[str, Any]:
    from 属性种子上下文 import PROJECTS
    from 种子验证 import new_seed_id, run_echidna, write_corpus
    if replay.get("replay_status") != "executable":
        return {"status": "skipped_no_anvil_executable_candidate"}
    context = candidate["context"]
    eligible = bool(replay.get("target_property_violation") or
                    (replay.get("target_property_state") or {}).get("property_related_state_changed") or
                    any(tx.get("status") == "success" for tx in replay.get("transactions", [])))
    if not eligible:
        return {"status": "skipped_no_effective_candidate"}
    property_name = str(prop.get("property_abi") or prop.get("property", "")).split("(", 1)[0].rsplit(".", 1)[-1]
    action_signatures = [item.get("abi_signature") for item in prop.get("candidate_actions", [])
                         if item.get("seed_compatible") and item.get("abi_signature")]
    filter_functions = [f"{PROJECTS[project]['contract']}.{signature}"
                        for signature in action_signatures]
    target_property = prop.get("property_abi", prop.get("property", ""))
    filter_functions.append(f"{PROJECTS[project]['contract']}.{property_name}()")
    out = RUN_ROOT / "05-Echidna-seed-only" / task_id / group
    corpus_root = out / "corpus-input"
    resolved = replay.get("resolved_transactions") or sequence
    seed_path = write_corpus(project, candidate, resolved, context, corpus_root,
                             replay=replay, seed_id=new_seed_id())
    run = run_echidna(project, out / "run", property_name=property_name,
                      test_limit=0, timeout=180, seed=20261125,
                      test_mode="property", property_prefix=property_name,
                      filter_functions=filter_functions,
                      seq_len=8, shrink_limit=1, stop_on_fail=False,
                      disable_slither=True, sender_pool=context.get("sender_pool"),
                      working_directory=Path(PROJECTS[project]["source_root"])
                      if Path(PROJECTS[project]["source_root"]).is_absolute()
                      else ROOT / PROJECTS[project]["source_root"])
    summary = {"task_id": task_id, "group": group,
               "status": "complete" if run.get("exit_code") == 0 or
               run.get("corpus_evidence", {}).get("property_failure_reported") else "echidna_failed",
               "anvil_seed": str(seed_path.relative_to(ROOT)),
               "test_limit": 0, "seed": 20261125,
               "expected_anvil_property": (replay.get("transactions", [{}])[-1].get("target_property")
                   if replay.get("transactions") else next(iter(replay.get("initial_property_values", {}).values()), None)),
               "echidna_property_failure": run.get("corpus_evidence", {}).get("property_failure_reported"),
               "loaded_seed_count": run.get("corpus_evidence", {}).get("loaded_seed_count"),
               "replayed_sequence_count": run.get("corpus_evidence", {}).get("replayed_sequence_count"),
               "exit_code": run.get("exit_code"),
               "elapsed_seconds": run.get("elapsed_seconds"),
               "full_log_path": run.get("full_log_path"),
               "raw_run": run}
    _write_json(out / "seed-only-summary.json", summary)
    return summary


def algorithm_run() -> None:
    if not FREEZE.is_file():
        raise FileNotFoundError("缺少冻结文件。")
    freeze_payload = _read_json(FREEZE)
    if not (RUN_ROOT / "02-预检总汇.json").is_file():
        raise FileNotFoundError("先完成独立 Oracle 与静态分析预检。")
    preflight_result = _read_json(RUN_ROOT / "02-预检总汇.json")
    if not preflight_result.get("agent_may_run"):
        raise RuntimeError("Oracle 或历史对照未确认；按停止规则不调用 Agent。")
    from 属性种子上下文 import PROJECTS, load_project_context
    from 种子验证 import replay_seed
    import Phase32有限扩展与对照 as extension_driver
    analysis_rows = _read_json(RUN_ROOT / "01-编译与静态分析" / "静态分析汇总.json")
    analysis_by_task = {row["task_id"]: row for row in analysis_rows}
    for task_id in ("BWorkflow", "BWorkflowRenamed", "CMsgSender", "DAllowance"):
        spec = TASK_SPECS[task_id]
        analysis = analysis_by_task[task_id]
        report_path = ROOT / analysis["report_path"]
        artifact_path = RUN_ROOT / "01-编译与静态分析" / task_id / "编译产物.json"
        spec["runtime_property_id"] = analysis["property_id"]
        spec["report_path"] = report_path
        spec["artifact_path"] = artifact_path
        _register_profile(task_id, spec, report_path, artifact_path)
    extension_driver.MAX_LENGTH = freeze_payload["frozen_algorithm_parameters"]["max_sequence_length"]
    extension_driver.MAX_EXECUTIONS = freeze_payload["frozen_algorithm_parameters"]["candidate_execution_budget_per_extension_method"]
    extension_driver.RETAINED_PREFIXES = freeze_payload["frozen_algorithm_parameters"]["retained_prefixes"]

    task_inputs: list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]] = []
    wallet_spec, wallet_context, wallet_prop, wallet_candidate, wallet_sequence, wallet_meta = _historical_wallet_input()
    task_inputs.append(("A_Wallet02Refund", wallet_spec, wallet_context, wallet_prop,
                        wallet_candidate, wallet_sequence, wallet_meta))

    for task_id in ("BWorkflow", "CMsgSender", "DAllowance"):
        spec = TASK_SPECS[task_id]
        candidate, agent_record = _agent_initial_candidate(task_id, spec)
        _write_json(RUN_ROOT / "03-Agent输入与输出" / task_id / "AgentAB初始种子.json", agent_record)
        if not candidate:
            _write_json(RUN_ROOT / "03-Agent输入与输出" / task_id / "停止记录.json", {
                "status": "未验证", "reason": agent_record.get("status"),
                "rule": "仅一次 Agent A/B 规划；不重试。"})
            continue
        context = candidate["context"]
        prop = context["properties"][0]
        task_inputs.append((task_id, spec, context, prop, candidate,
                            copy.deepcopy(candidate["transactions"]),
                            {"agent_calls_this_audit": agent_record.get("api_call_count"),
                             "agent_tokens": agent_record.get("api_usage"),
                             "agent_record": str((RUN_ROOT / "03-Agent输入与输出" / task_id / "AgentAB初始种子.json").relative_to(ROOT))}))

    phase32r = _load_phase32r_driver()
    pigfox_spec, pigfox_context, pigfox_prop, pigfox_candidate, pigfox_sequence, pigfox_meta = _historical_pigfox_input(phase32r)
    pigfox_spec["goal"] = {"kind": "rwa_supply_sum",
                            "property": "echidna_supply_equals_sum_of_balances()",
                            "expected_property": True,
                            "low_dependency_negative_control": True}
    task_inputs.append(("E_PigfoxRWASupplySum", pigfox_spec, pigfox_context, pigfox_prop,
                        pigfox_candidate, pigfox_sequence, pigfox_meta))

    summaries = []
    echidna_rows = []
    for task_id, spec, context, prop, candidate, sequence, metadata in task_inputs:
        candidate["context"] = context
        goal = spec.get("goal")
        if not goal:
            goal = {"kind": "wallet_counterexample"}
        main_row = _run_extension(task_id, spec["project"], prop,
                                  candidate, sequence,
                                  {**metadata, "goal": goal})
        summaries.append(main_row["summary"])
        e1_replay = main_row["E1_replay"]
        if (e1_replay.get("replay_status") == "executable" and
                (e1_replay.get("target_property_violation") or
                 (e1_replay.get("target_property_state") or {}).get("property_related_state_changed") or
                 any(tx.get("status") == "success" for tx in e1_replay.get("transactions", [])))):
            echidna_rows.append({"task_id": task_id, "group": "E1",
                                 **_run_echidna_confirmation(task_id, "E1", candidate, prop,
                                                             sequence, e1_replay, spec["project"])})
        for group, summary in main_row["method_summaries"].items():
            selected = next((row for row in summary.get("candidates", [])
                             if row.get("replay_status") == "executable" and
                             (row.get("target_state", {}).get("reached") or
                              row.get("target_state", {}).get("property_related_state_changed"))), None)
            if selected:
                raw = selected["extension_record"]
                replay = raw.get("replay", {})
                echidna_rows.append({"task_id": task_id, "group": group,
                                     **_run_echidna_confirmation(
                                         task_id, group, candidate, prop,
                                         selected.get("sequence", []), replay, spec["project"])})
        # B's frozen name-only variant reuses the same Agent E1 sequence and makes no model call.
        if task_id == "BWorkflow":
            variant_task = TASK_SPECS["BWorkflowRenamed"]
            variant_context = load_project_context(
                variant_task["project"], [variant_task["runtime_property_id"]])
            variant_prop = variant_context["properties"][0]
            variant_context = {**variant_context, "properties": [variant_prop],
                               "sender_pool": list(PROJECTS[variant_task["project"]].get("senders") or SENDERS)}
            variant_sequence = _translate_variant(sequence, variant_task["rename_map"])
            unknown = [tx["function"] for tx in variant_sequence
                       if tx["function"] not in {item.get("abi_signature") for item in variant_prop.get("candidate_actions", [])}]
            variant_candidate = {"project": variant_task["project"],
                                 "property_id": variant_task["runtime_property_id"],
                                 "candidate_id": candidate.get("candidate_id", "renamed-B-seed"),
                                 "transactions": variant_sequence,
                                 "property": variant_prop["property"],
                                 "context": variant_context}
            if unknown:
                variant_summary = {"task_id": "BWorkflowRenamed", "status": "未验证",
                                   "reason": "冻结的函数名一一映射未能匹配 Agent 序列：" + ", ".join(unknown),
                                   "agent_calls": 0}
                _write_json(RUN_ROOT / "04-Anvil对照/BWorkflowRenamed-未验证.json", variant_summary)
            else:
                variant_result = _run_extension(
                    "BWorkflowRenamed", variant_task["project"], variant_prop,
                    variant_candidate, variant_sequence,
                    {"goal": variant_task["goal"], "agent_calls_this_audit": 0,
                     "renamed_from": "BWorkflow", "name_only_mapping": variant_task["rename_map"]})
                summaries.append(variant_result["summary"])

    _write_json(RUN_ROOT / "05-Echidna-seed-only/seed-only-index.json", echidna_rows)
    final = {"status": "complete", "freeze_sha256": _sha(FREEZE),
             "scenarios": summaries, "echidna_seed_only": echidna_rows,
             "model_calls": {row["task_id"]: row.get("metadata", {}) for row in summaries},
             "core_algorithm_changed": False,
             "human_oracle_passed_to_algorithm": False,
             "note": "目标到达、属性相关状态改变、交易成功、参数修复和重复操作分开归因。"}
    _write_json(RUN_ROOT / "06-审计总汇.json", final)
    print(json.dumps({"status": final["status"],
                      "tasks": [row["task_id"] for row in summaries],
                      "result": str((RUN_ROOT / "06-审计总汇.json").relative_to(ROOT))}, ensure_ascii=False))


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--algorithm", action="store_true")
    args = parser.parse_args()
    if args.freeze_only:
        freeze_inputs()
    elif args.preflight:
        preflight()
    elif args.algorithm:
        algorithm_run()
    else:
        parser.error("选择 --freeze-only、--preflight 或 --algorithm 中的一项")


if __name__ == "__main__":
    main()
