#!/usr/bin/env python3
"""Fast mechanism tests for Phase37 prerequisite binding and Phase36 cache safety."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "func/功能"),
                str(ROOT / "func/测试过程/跨交易属性状态依赖审计")]

from 跨交易状态约束 import bind_inserted_prerequisite
from Phase36属性状态感知门控 import AdaptiveGate
import 属性种子上下文


OWNER = "0x0000000000000000000000000000000000010000"
OPERATOR = "0x0000000000000000000000000000000000020000"
RECIPIENT = "0x0000000000000000000000000000000000030000"


def _abi(**items):
    return {signature: {"inputs": inputs} for signature, inputs in items.items()}


class PrerequisiteBindingTests(unittest.TestCase):
    def test_numeric_writer_bound_from_consumer_guard(self):
        parent = [
            {"function": "createTask()", "arguments": [], "sender": OWNER, "value_wei": "0"},
            {"function": "executeTask(uint256)", "arguments": [3], "sender": OPERATOR, "value_wei": "0"},
        ]
        child = [parent[0],
            {"function": "configureTask(uint256)", "arguments": [1], "sender": OWNER, "value_wei": "0"},
            parent[1],
        ]
        effects = {
            "write": {"state": "WorkflowHarness.executionLimit",
                "writer": "WorkflowHarness.configureTask(uint256)",
                "expression": "executionLimit = maxAmount", "source": "Workflow.sol#15"},
            "read": {"state": "WorkflowHarness.completedAmount",
                "writer": "WorkflowHarness.executeTask(uint256)", "expression": "completedAmount += amount",
                "guards": [{"expression": "require(bool,string)(amount > 0 && amount <= executionLimit,LIMIT_EXCEEDED)",
                    "state_reads": ["WorkflowHarness.executionLimit"], "source": "Workflow.sol#24"}]},
        }
        abi = _abi(**{
            "createTask()": [],
            "configureTask(uint256)": [{"name": "maxAmount", "type": "uint256"}],
            "executeTask(uint256)": [{"name": "amount", "type": "uint256"}],
        })
        original = copy.deepcopy(parent)
        result = bind_inserted_prerequisite(parent, child, effects, abi)
        self.assertIsNotNone(result)
        self.assertEqual(result["sequence"][1]["arguments"], [3])
        self.assertEqual(parent, original)
        self.assertEqual(result["evidence"]["numeric_constraint"]["satisfying_range"]["minimum"], 3)

    def test_msg_sender_role_binds_mapping_index_and_value(self):
        parent = [
            {"function": "fundCredit()", "arguments": [], "sender": OWNER, "value_wei": "1"},
            {"function": "executeFor(address,uint256)", "arguments": [OWNER, 1], "sender": OPERATOR, "value_wei": "0"},
        ]
        child = [parent[0],
            {"function": "authorizeOperator(address)", "arguments": [OWNER], "sender": OWNER, "value_wei": "0"},
            parent[1],
        ]
        effects = {
            "write": {"state": "DelegationHarness.authorizedOperator",
                "writer": "DelegationHarness.authorizeOperator(address)",
                "expression": "authorizedOperator[msg.sender] = operator", "source": "Delegation.sol#20"},
            "read": {"state": "DelegationHarness.executedFor",
                "writer": "DelegationHarness.executeFor(address,uint256)", "expression": "executedFor[owner] += amount",
                "guards": [{"expression": "require(bool,string)(authorizedOperator[owner] == msg.sender,NOT_AUTHORIZED_OPERATOR)",
                    "state_reads": ["DelegationHarness.authorizedOperator"], "source": "Delegation.sol#25"}]},
        }
        abi = _abi(**{
            "fundCredit()": [],
            "authorizeOperator(address)": [{"name": "operator", "type": "address"}],
            "executeFor(address,uint256)": [{"name": "owner", "type": "address"},
                {"name": "amount", "type": "uint256"}],
        })
        result = bind_inserted_prerequisite(parent, child, effects, abi)
        self.assertIsNotNone(result)
        bound = result["sequence"][1]
        self.assertEqual(bound["sender"], OWNER)
        self.assertEqual(bound["arguments"], [OPERATOR])

    def test_allowance_binds_both_keys_and_sufficient_value(self):
        parent = [
            {"function": "mint(address,uint256)", "arguments": [OWNER, 10], "sender": OWNER, "value_wei": "0"},
            {"function": "transferFrom(address,address,uint256)", "arguments": [OWNER, RECIPIENT, 4], "sender": OPERATOR, "value_wei": "0"},
        ]
        child = [parent[0],
            {"function": "approve(address,uint256)", "arguments": [OWNER, 10], "sender": OWNER, "value_wei": "0"},
            parent[1],
        ]
        effects = {
            "write": {"state": "AllowanceHarness.allowance",
                "writer": "AllowanceHarness.approve(address,uint256)",
                "expression": "allowance[msg.sender][spender] = amount", "source": "Allowance.sol#24"},
            "read": {"state": "AllowanceHarness.delegatedSpent",
                "writer": "AllowanceHarness.transferFrom(address,address,uint256)",
                "expression": "delegatedSpent[owner][msg.sender] += amount",
                "guards": [{"expression": "require(bool,string)(allowance[owner][msg.sender] >= amount,ALLOWANCE_TOO_LOW)",
                    "state_reads": ["AllowanceHarness.allowance"], "source": "Allowance.sol#30"}]},
        }
        abi = _abi(**{
            "mint(address,uint256)": [{"name": "recipient", "type": "address"},
                {"name": "amount", "type": "uint256"}],
            "approve(address,uint256)": [{"name": "spender", "type": "address"},
                {"name": "amount", "type": "uint256"}],
            "transferFrom(address,address,uint256)": [{"name": "owner", "type": "address"},
                {"name": "recipient", "type": "address"}, {"name": "amount", "type": "uint256"}],
        })
        result = bind_inserted_prerequisite(parent, child, effects, abi)
        self.assertIsNotNone(result)
        bound = result["sequence"][1]
        self.assertEqual(bound["sender"], OWNER)
        self.assertEqual(bound["arguments"], [OPERATOR, 4])

    def test_writer_after_consumer_is_not_bound(self):
        parent = [{"function": "consume(uint256)", "arguments": [3], "sender": OPERATOR}]
        child = [parent[0], {"function": "configure(uint256)", "arguments": [1], "sender": OWNER}]
        effects = {
            "writer": {"state": "H.limit", "writer": "H.configure(uint256)",
                       "expression": "limit = max"},
            "consumer": {"state": "H.used", "writer": "H.consume(uint256)",
                         "guards": [{"expression": "require(bool)(amount <= limit)",
                                     "state_reads": ["H.limit"]}]},
        }
        abi = _abi(**{"consume(uint256)": [{"name": "amount", "type": "uint256"}],
                     "configure(uint256)": [{"name": "max", "type": "uint256"}]})
        self.assertIsNone(bind_inserted_prerequisite(parent, child, effects, abi))

    def test_phase36_frozen_traces_bind_from_real_slither_and_abi_artifacts(self):
        phase36_root = ROOT / "func/测试过程/跨交易属性状态依赖审计/结果/Phase36-20261120"
        frozen = json.loads((phase36_root / "00-Phase36冻结.json").read_text(encoding="utf-8"))
        expected = {
            "BWorkflow": ("configureTask(uint256)", 0, 3, None),
            "CMsgSender": ("authorizeOperator(address)", 0, OPERATOR, OWNER),
            "DAllowance": ("approve(address,uint256)", 1, 4, OWNER),
        }
        for task_id, (writer_signature, argument_index, wanted_value, wanted_sender) in expected.items():
            with self.subTest(task_id=task_id):
                task = frozen["missing_prerequisite_safety_inputs"][task_id]
                raw_path = (phase36_root / "SafetyMissingPrerequisite" / task_id /
                            "G1" / "G1-原始E3.json")
                raw = json.loads(raw_path.read_text(encoding="utf-8"))
                record = next(item for item in raw["records"]
                              if any(tx.get("function") == writer_signature
                                     for tx in item.get("sequence", [])) and
                              item.get("candidate_no", 0) > 0)
                report_path = (ROOT / "func/测试过程/跨交易属性状态依赖审计/结果/20261120/01-编译与静态分析" /
                               task_id / "属性分析.json")
                artifact_path = report_path.with_name("编译产物.json")
                report = json.loads(report_path.read_text(encoding="utf-8"))
                artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
                abi = {entry["name"] + "(" + ",".join(arg["type"] for arg in entry.get("inputs", [])) + ")": entry
                       for entry in artifact["abi"] if entry.get("type") == "function"}
                result = bind_inserted_prerequisite(task["sequence"], record["sequence"],
                    report["effect_catalog"], abi,
                    parent_replay=(raw.get("records") or [{}])[0].get("replay"))
                self.assertIsNotNone(result)
                producer = result["sequence"][result["evidence"]["producer_index"] - 1]
                self.assertEqual(producer["function"], writer_signature)
                self.assertEqual(producer["arguments"][argument_index], wanted_value)
                if task_id == "DAllowance":
                    self.assertEqual(producer["arguments"][0], OPERATOR)
                if wanted_sender is not None:
                    self.assertEqual(producer["sender"], wanted_sender)
                self.assertTrue(result["evidence"]["writer_source"])
                self.assertTrue(result["evidence"]["guard_source"])


class AdaptiveGateCacheTests(unittest.TestCase):
    def _replay(self, state_fingerprint: str, balance: int, supply: int):
        return {"replay_status": "executable", "transactions": [{
            "status": "success", "state_fingerprint_after": state_fingerprint,
            "predicate_getter_values": [
                {"signature": "balanceOf(address)", "arguments": [OWNER],
                 "receiver_address": "0x0000000000000000000000000000000000000010",
                 "status": "observed", "value": balance},
                {"signature": "totalSupply()", "arguments": [],
                 "receiver_address": "0x0000000000000000000000000000000000000010",
                 "status": "observed", "value": supply},
            ]}],
        }

    def test_cached_skip_requires_same_parent_state(self):
        prop = {"property_predicate": "uint256 sum; sum += token.balanceOf(holder); return sum == token.totalSupply();"}
        gate = AdaptiveGate(prop, 8)
        repeated = {"function": "mint(address,uint256)", "arguments": [OWNER, 1],
                    "sender": OWNER, "value_wei": "0"}
        parent_sequence = [repeated]
        child_sequence = [repeated, repeated]
        parent = self._replay("parent-A", 10, 10)
        child = self._replay("child-A", 11, 11)
        proposal = {"operator": "state_supported_repetition", "sequence": child_sequence}
        first = gate.decide(proposal, parent, parent_sequence)
        self.assertEqual(first["action"], "extend")
        self.assertIsNotNone(gate.observe(first.get("repeat_key"), parent, child,
                                          parent_sequence, child_sequence))

        same_state = gate.decide(proposal, parent, parent_sequence)
        self.assertEqual(same_state["action"], "skip")
        changed_state = gate.decide(proposal, self._replay("parent-B", 20, 20), parent_sequence)
        self.assertEqual(changed_state["action"], "extend")
        self.assertIn("different", changed_state["reason"])


class MountedSourceFallbackTests(unittest.TestCase):
    def test_inaccessible_root_copy_falls_back_to_project_source_root(self):
        project = "Phase37PermissionFallback"
        属性种子上下文.PROJECTS[project] = {"source_root": "project-root"}
        root_candidate = 属性种子上下文.ROOT / "src" / "Contract.sol"
        fallback_candidate = 属性种子上下文.ROOT / "project-root" / "src" / "Contract.sol"

        def is_file(path):
            if path == root_candidate:
                raise PermissionError("simulated inaccessible mount entry")
            return path == fallback_candidate

        try:
            with patch.object(Path, "is_file", is_file):
                resolved = 属性种子上下文._resolve_source(project, "src/Contract.sol")
            self.assertEqual(resolved, fallback_candidate)
        finally:
            属性种子上下文.PROJECTS.pop(project, None)


if __name__ == "__main__":
    unittest.main()
