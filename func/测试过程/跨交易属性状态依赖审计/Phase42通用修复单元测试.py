#!/usr/bin/env python3
"""Generic regression tests for evidence-based numeric repair, E3 and feedback."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "func/功能"))

from 跨交易状态约束 import (cross_transaction_write_read_matches,
                           extract_numeric_guard_evidence,
                           propose_numeric_repair,
                           propagate_argument_updates)
from 状态反馈序列扩展 import feedback_vector, propose_extensions
from 真实合约统一执行适配器 import execution_feedback_to_v2


class Phase42GenericRepairTests(unittest.TestCase):
    def test_getter_and_source_guard_prove_lower_bound(self) -> None:
        inputs = [{"name": "quantity", "type": "uint64"}]
        guards = extract_numeric_guard_evidence([{
            "source": "contracts/Rate.sol",
            "text": 'require(quantity >= _minimumQuantity, "requested quantity below minimum");'
        }], inputs)
        proposal = propose_numeric_repair(
            inputs, [3], [{"outputs": [{"name": "minimumQuantity", "type": "uint64",
                                         "value": 11}]}],
            ["requested quantity below minimum"], static_guards=guards)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal["repair_mode"], "observed_numeric_lower_bound")
        self.assertEqual(proposal["repaired_value"], 11)
        self.assertIn("Rate.sol", proposal["slither_guards"][0]["source"])

    def test_lower_bound_requires_matching_guard_and_failure_evidence(self) -> None:
        inputs = [{"name": "quantity", "type": "uint64"}]
        observation = [{"outputs": [{"name": "minimumQuantity", "type": "uint64",
                                     "value": 11}]}]
        unrelated = [{"expression": "balance >= _minimumBalance",
                      "left_identifier": "balance", "operator": ">=",
                      "right_identifier": "_minimumBalance"}]
        self.assertIsNone(propose_numeric_repair(
            inputs, [3], observation, ["requested quantity below minimum"],
            static_guards=unrelated))
        matching = [{"expression": "quantity >= _minimumQuantity",
                     "left_identifier": "quantity", "operator": ">=",
                     "right_identifier": "_minimumQuantity"}]
        self.assertIsNone(propose_numeric_repair(
            inputs, [3], observation, ["unrelated failure"], static_guards=matching))

    def test_existing_getter_upper_bound_repair_remains_available(self) -> None:
        proposal = propose_numeric_repair(
            [{"name": "limit", "type": "uint32"}], [99],
            [{"outputs": [{"name": "maximumLimit", "type": "uint32", "value": 15}]}],
            ["maximum limit exceeded"])
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal["repaired_value"], 15)
        self.assertEqual(proposal["repair_mode"], "observed_numeric_upper_bound")

    def test_repair_propagates_only_explicitly_linked_fields(self) -> None:
        sequence = [
            {"function": "submit(uint32)", "arguments": [2]},
            {"function": "check(uint32,uint32)", "arguments": [2, 91],
             "data_dependencies": [{"from_transaction": 1,
                                    "fields": ["limit -> checkedLimit"]}]},
            {"function": "unrelated(uint32)", "arguments": [2]},
        ]
        repaired, trace = propagate_argument_updates(
            sequence, 0,
            {"argument_updates": [{"argument_index": 0, "argument_name": "limit",
                                   "repaired_value": 15}]},
            {"check(uint32,uint32)": {"inputs": [
                {"name": "checkedLimit", "type": "uint32"},
                {"name": "other", "type": "uint32"}]}})
        self.assertEqual(repaired[0]["arguments"], [15])
        self.assertEqual(repaired[1]["arguments"], [15, 91])
        self.assertEqual(repaired[2]["arguments"], [2])
        self.assertEqual(len(trace), 2)

    def test_e3_inserts_evidenced_prerequisite_before_first_failure(self) -> None:
        sequence = [{"function": "consume(uint256)", "arguments": [4]}]
        actions = [{"function": "prepare(uint256)", "arguments": [0]}]
        evidence = {
            "consume(uint256)": {"read_states": ["Ledger.entries"],
                                 "action_guard_evidence": [{
                                     "state_reads": ["Ledger.entries"],
                                     "source": "Ledger.sol:guard"}]},
            "prepare(uint256)": {"write_states": ["Ledger.entries"]},
        }
        rows = propose_extensions(
            sequence, actions, evidence,
            {"prepare(uint256)": {"inputs": [{"name": "key", "type": "uint256"}]}},
            mode="state_feedback", replay={"transactions": [{"index": 1,
                "function": "consume(uint256)", "status": "reverted",
                "revert_reason": "entry not found"}]},
            max_proposals=4)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["operator"], "evidence_backed_failed_prerequisite_insertion")
        self.assertEqual(rows[0]["evidence"]["failed_transaction"], 1)
        self.assertEqual(rows[0]["sequence"][0]["function"], "prepare(uint256)")

    def test_e3_does_not_spend_budget_on_broad_matches_or_numeric_failures(self) -> None:
        sequence = [{"function": "consume(uint256)", "arguments": [4]}]
        actions = [{"function": "prepare(uint256)", "arguments": [0]}]
        abi = {"prepare(uint256)": {"inputs": [{"name": "key", "type": "uint256"}]}}
        broad = {"consume(uint256)": {},
                 "prepare(uint256)": {"matched_states": ["Ledger.entries"]}}
        self.assertEqual(propose_extensions(
            sequence, actions, broad, abi, mode="state_feedback",
            target_states={"Ledger.entries"}, max_proposals=4), [])
        precise = {"consume(uint256)": {"read_states": ["Ledger.entries"]},
                   "prepare(uint256)": {"write_states": ["Ledger.entries"]}}
        self.assertEqual(propose_extensions(
            sequence, actions, precise, abi, mode="state_feedback",
            replay={"transactions": [{"index": 1,
                "function": "consume(uint256)", "status": "reverted",
                "revert_reason": "quantity too low"}]}, max_proposals=4), [])

    def test_phase37_gate_reports_only_exact_writer_guard_state_overlap(self) -> None:
        parent = [{"function": "consume(uint256)", "arguments": [5]}]
        child = [{"function": "prepare(uint256)", "arguments": [0]}, *parent]
        catalog = [
            {"writer": "prepare(uint256)", "state": "Ledger.items",
             "expression": "items[key] = value"},
            {"writer": "consume(uint256)", "state": "Other.state",
             "guards": [{"state_reads": ["Ledger.items"],
                         "expression": "items[key] >= value"}]},
        ]
        matches = cross_transaction_write_read_matches(parent, child, catalog)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["state"], "Ledger.items")
        self.assertEqual(cross_transaction_write_read_matches(
            parent, child, [{"writer": "prepare(uint256)", "state": "Ledger.items"}]), [])

    def test_e3_retains_latest_target_check_before_trailing_transaction(self) -> None:
        vector = feedback_vector({
            "replay_status": "executable",
            "transactions": [
                {"status": "success", "target_property": True,
                 "target_property_status": "passed"},
                {"status": "success", "target_property": None},
            ],
            "target_property_state": {"counterexample_state_established": False},
        })
        self.assertTrue(vector["replay_complete"])
        self.assertTrue(vector["property_value"])
        self.assertEqual(vector["property_check_transaction_index"], 1)
        self.assertEqual(vector["property_check_status"], "passed")
        self.assertFalse(vector["counterexample_reached"])

    def test_e3_does_not_use_unrelated_initial_property_as_target_value(self) -> None:
        vector = feedback_vector({
            "replay_status": "executable",
            "transactions": [{"status": "success", "target_property": None}],
            "target_property_state": {"property": "Harness.targetInvariant()"},
            "initial_property_values": {"Harness.otherInvariant()": True},
        })
        self.assertIsNone(vector["property_value"])
        self.assertEqual(vector["property_check_status"], "unknown")
        self.assertFalse(vector["counterexample_reached"])

    def test_target_assertion_signature_accepts_contract_prefix(self) -> None:
        feedback = execution_feedback_to_v2({
            "backend": "foundry-cheatcode", "status": "passed",
            "execution": {"status": "passed", "deployment": {"success": True},
                "transactions": [{"index": 1, "function": "check(uint256)",
                                  "arguments": [1], "sender": "0x1", "status": "success",
                                  "return_data": "0x", "property_checks": [],
                                  "observations_before": [], "observations_after": []}],
                "properties": []}}, {},
            target_property_signature="Harness.check(uint256)")
        self.assertEqual(feedback["replay_status"], "executable")
        self.assertTrue(feedback["property_checks_passed"])
        self.assertEqual(feedback["transactions"][0]["target_property_status"], "passed")

    def test_property_getter_signature_accepts_contract_prefix(self) -> None:
        observation = lambda value, label: {"name": label,
            "signature": "isBalanced()", "receiver": label, "arguments": [],
            "output_type": "bool", "value": value, "status": "success"}
        feedback = execution_feedback_to_v2({
            "backend": "anvil-rpc", "status": "replay_completed",
            "execution": {"status": "replay_completed",
                "deployment": {"success": True},
                "transactions": [{"index": 1, "function": "move(uint256)",
                                  "arguments": [1], "sender": "0x1", "status": "success"}],
                "state_before": [observation("True", "property_before")],
                "state_after": [observation("False", "property_after")],
                "properties": []}}, {},
            target_property_signature="LedgerHarness.isBalanced()")
        self.assertEqual(feedback["replay_status"], "replay_failed")
        self.assertTrue(feedback["target_property_state"]["counterexample_state_established"])
        self.assertFalse(feedback["property_checks_passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
