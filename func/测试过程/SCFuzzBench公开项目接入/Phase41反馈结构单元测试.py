#!/usr/bin/env python3
"""验证统一执行反馈转换器保留逐笔事实并将不可观察状态标为 unknown。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "func/功能"))

from 真实合约统一执行适配器 import execution_feedback_to_v2, _foundry_toml
from 状态反馈序列扩展 import feedback_vector


ADDRESS = "0x0000000000000000000000000000000000010000"
PANIC_ASSERT = "0x4e487b71" + "0" * 62 + "01"
PANIC_OVERFLOW = "0x4e487b71" + "0" * 62 + "11"


def observation(value: str, *, success: bool = True) -> dict:
    row = {"name": "splittable", "signature": "splittable(uint256,address)",
           "receiver": "harness", "receiver_address": "0x" + "ab" * 20,
           "arguments": [131072, ADDRESS], "output_type": "uint128",
           "success": success, "raw": value,
           "source": {"backend": "foundry-cheatcode", "phase": "after"}}
    if success:
        row["value"] = value
    return row


def backend_result(*, target_status: str = "success", target_return: str = "0x") -> dict:
    return {
        "backend": "foundry-cheatcode", "status": "passed",
        "log": "/experiment/target.foundry.log",
        "driver_source": "/experiment/driver/test/Phase40Replay.t.sol",
        "execution": {
            "status": "passed", "deployment": {"success": True, "target_address": "0x" + "cd" * 20},
            "initial_observations": [observation("0")],
            "properties": [{"after_transaction": 1, "signature": "invariant()",
                            "success": True, "return_data": "0x"}],
            "transactions": [{
                "index": 1, "function": "testCheck(uint8)", "arguments": [7],
                "sender": ADDRESS, "origin": ADDRESS, "value_wei": "9",
                "status": target_status, "return_data": target_return,
                "gas_used_estimate": 120000, "timestamp_before": 1524785992,
                "timestamp_at_call": 1524785993, "timestamp_after": 1524785994,
                "block_number": 4370001,
                "observations_before": [observation("0")],
                "observations_after": [observation("2")],
                "property_checks": [{"after_transaction": 1, "signature": "invariant()",
                                     "success": True, "return_data": "0x"}],
            }],
        },
    }


class FeedbackContractTest(unittest.TestCase):
    def setUp(self):
        self.manifest = {"observers": [{"name": "splittable",
                                       "signature": "splittable(uint256,address)",
                                       "predicate_observer": False}]}

    def test_transaction_fields_and_observed_state_survive(self):
        result = execution_feedback_to_v2(
            backend_result(), self.manifest, target_property_signature="testCheck(uint8)")
        row = result["transactions"][0]
        self.assertEqual(row["status"], "success")
        self.assertEqual(row["function"], "testCheck(uint8)")
        self.assertEqual(row["arguments"], [7])
        self.assertEqual(row["sender"], ADDRESS)
        self.assertEqual(row["origin"], ADDRESS)
        self.assertEqual(row["value_wei"], "9")
        self.assertEqual(row["timestamp_at_call"], 1524785993)
        self.assertEqual(row["gas_used"], None)
        self.assertEqual(row["gas_used_estimate"], 120000)
        self.assertTrue(row["target_property"])
        self.assertEqual(result["state_changes"][0]["before"], "0")
        self.assertEqual(result["state_changes"][0]["after"], "2")
        self.assertEqual(result["target_property_state"]["trajectory"][1]["value"], True)
        self.assertEqual(result["target_property_state"]["property_related_state_changed"], None)
        self.assertEqual(result["target_property_state"]["status"], "property_check_passed")
        self.assertEqual(result["unknown_fields"][0]["status"], "unknown")

    def test_only_assertion_panic_is_a_counterexample(self):
        failed_assertion = execution_feedback_to_v2(
            backend_result(target_status="reverted", target_return=PANIC_ASSERT),
            self.manifest, target_property_signature="testCheck(uint8)")
        self.assertFalse(failed_assertion["transactions"][0]["target_property"])
        self.assertTrue(failed_assertion["target_property_state"]["counterexample_state_established"])
        unrelated_revert = execution_feedback_to_v2(
            backend_result(target_status="reverted", target_return=PANIC_OVERFLOW),
            self.manifest, target_property_signature="testCheck(uint8)")
        self.assertIsNone(unrelated_revert["transactions"][0]["target_property"])
        self.assertEqual(unrelated_revert["transactions"][0]["target_property_status"], "unknown")

    def test_manifest_binds_only_the_declared_assertion_invoked_in_sequence(self):
        result = execution_feedback_to_v2(
            backend_result(), {"native_assertions": ["testCheck(uint8)"]})
        self.assertEqual(result["target_property_signature_source"],
                         "manifest_declared_assertion_invoked_by_sequence")
        self.assertEqual(result["target_property_state"]["property"], "testCheck(uint8)")
        self.assertTrue(result["transactions"][0]["target_property"])
        self.assertEqual(result["target_property_state"]["status"],
                         "property_check_passed")

    def test_e3_consumes_feedback_without_claiming_missing_predicate_values(self):
        result = execution_feedback_to_v2(
            backend_result(), self.manifest, target_property_signature="testCheck(uint8)")
        vector = feedback_vector(result, property_source="assert(x == y)")
        self.assertEqual(vector["transactions_succeeded"], 1)
        self.assertTrue(vector["replay_complete"])
        self.assertIsNone(vector["numeric_target_distance"])
        self.assertFalse(vector["counterexample_reached"])
        self.assertEqual(result["transactions"][0]["predicate_getter_values"], [])

    def test_anvil_sequence_endpoints_are_not_fabricated_as_per_transaction_state(self):
        prop = "echidna_wallet_accounting_respected()"
        before = [
            {"label": "property_before", "function": prop, "arguments": [],
             "value": "True", "status": "success"},
            {"label": "deposits_before", "function": "cumulativeDeposits(uint8)",
             "arguments": [0], "value": "1000000000000000000", "status": "success"},
            {"label": "payout_before", "function": "cumulativePayout(uint8)",
             "arguments": [0], "value": "1000000000000000000", "status": "success"},
        ]
        after = [
            {"label": "property_after", "function": prop, "arguments": [],
             "value": "False", "status": "success"},
            {"label": "deposits_after", "function": "cumulativeDeposits(uint8)",
             "arguments": [1], "value": "1000000000000000000", "status": "success"},
            {"label": "payout_after", "function": "cumulativePayout(uint8)",
             "arguments": [0], "value": "2000000000000000000", "status": "success"},
        ]
        raw = {"backend": "anvil-rpc", "status": "replay_completed",
               "execution": {"status": "replay_completed",
                             "deployment": {"status": 1, "contract_address": "0x" + "cd" * 20},
                             "state_before": before,
                             "transactions": [{"index": i, "function": "step(uint8)",
                                               "arguments": [i], "sender": ADDRESS,
                                               "value_wei": "0", "status": 1,
                                               "gas_used": 21000, "block_number": i + 1}
                                              for i in range(1, 5)],
                             "state_after": after}}
        manifest = {"target_state_check": {"getter_signatures": [
            "cumulativeDeposits(uint8)", "cumulativePayout(uint8)"]}}
        result = execution_feedback_to_v2(
            raw, manifest, target_property_signature=prop)
        self.assertTrue(result["deployment"]["success"])
        self.assertTrue(result["sequence_success"])
        self.assertFalse(result["transactions"][-1]["target_property"])
        self.assertTrue(result["target_property_state"]["counterexample_state_established"])
        self.assertEqual(result["target_property_state"]["trajectory"][-1]["observation_scope"],
                         "after_sequence")
        self.assertFalse(result["capabilities"]["per_transaction_state_observation"])
        self.assertTrue(any(row["field"] == "transactions.per_transaction_state_observations"
                            for row in result["unknown_fields"]))
        self.assertTrue(any(row["signature"] == "cumulativePayout(uint8)"
                            for row in result["sequence_state_changes"]))

    def test_foundry_environment_matches_declared_runtime(self):
        config = _foundry_toml(
            {"build": {"source_directory": "src", "solc_version": "0.8.20"},
             "remappings": [], "execution": {
                 "deployment_timestamp": 1524785992, "deployment_block_number": 4370000,
                 "chain_id": 1, "gas_price": 0}},
            Path("/tmp/source"), Path("/tmp/driver"), Path("/tmp/output"))
        self.assertIn("block_timestamp = 1524785992", config)
        self.assertIn("block_number = 4370000", config)
        self.assertIn("chain_id = 1", config)
        self.assertIn("gas_price = 0", config)


if __name__ == "__main__":
    unittest.main()
