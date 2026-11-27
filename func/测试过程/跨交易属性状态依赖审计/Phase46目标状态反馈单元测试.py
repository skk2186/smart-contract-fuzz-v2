#!/usr/bin/env python3
"""Phase46 focused tests for directional target and prerequisite feedback."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "func/功能"))
sys.path.insert(0, str(ROOT / "func/测试过程/跨交易属性状态依赖审计"))

from 状态反馈序列扩展 import feedback_vector, propose_extensions, retain_diverse_prefixes
from Phase36自适应扩展 import _property_source_for_feedback


SENDER = "0x0000000000000000000000000000000000010000"


def getter(signature: str, value: int) -> dict:
    return {"signature": signature, "arguments": [0], "status": "observed", "value": value}


class TargetProgressTests(unittest.TestCase):
    def test_numeric_property_uses_same_operands_and_direction(self):
        source = "return values[i] >= limits[i]"
        parent = {"replay_status": "executable", "transactions": [{
            "status": "success", "target_property": True,
            "predicate_getter_values": [getter("values(uint256)", 2),
                                        getter("limits(uint256)", 10)]}]}
        child = {"replay_status": "executable", "transactions": [{
            "status": "success", "target_property": True,
            "predicate_getter_values": [getter("values(uint256)", 9),
                                        getter("limits(uint256)", 10)]}]}
        parent_vector = feedback_vector(parent, property_source=source)
        child_vector = feedback_vector(child, property_source=source,
                                       parent_vector=parent_vector)
        self.assertEqual(child_vector["target_progress"]["status"], "directional_progress")
        self.assertEqual(child_vector["target_progress"]["direction"], "toward_violation")
        self.assertAlmostEqual(child_vector["target_progress"]["evidence"]["previous_distance"], 0.8)
        self.assertAlmostEqual(child_vector["target_progress"]["evidence"]["current_distance"], 0.1)

    def test_boolean_property_is_not_converted_to_numeric_distance(self):
        replay = {"replay_status": "executable", "transactions": [{
            "status": "success", "target_property": True,
            "predicate_getter_values": [{"signature": "bug()", "arguments": [],
                                          "status": "observed", "value": False}]}]}
        vector = feedback_vector(replay, property_source="return !bug")
        self.assertIsNone(vector["numeric_target_distance"])
        self.assertEqual(vector["target_progress"]["status"],
                         "observed_safe_no_directional_progress")

    def test_static_guard_and_replay_confirm_prerequisite_progress(self):
        evidence = {
            "configure(uint256)": {"write_states": ["H.allowance"]},
            "consume(uint256)": {"effect_evidence": [{
                "guards": [{"source": "H.sol#12", "state_reads": ["H.allowance"],
                            "expression": "require(allowance[owner][msg.sender] >= amount, ALLOWANCE_TOO_LOW)"}]}]},
        }
        failed = {"replay_status": "failed", "transactions": [{
            "function": "consume(uint256)", "arguments": [4], "status": "outer_revert",
            "property_error": "execution reverted: ALLOWANCE_TOO_LOW"}]}
        succeeded = {"replay_status": "executable", "transactions": [
            {"function": "configure(uint256)", "status": "success",
             "changed_effect_states": ["H.allowance"]},
            {"function": "consume(uint256)", "arguments": [4], "status": "success"}]}
        parent = feedback_vector(failed, action_evidence=evidence)
        child = feedback_vector(succeeded, action_evidence=evidence, parent_vector=parent)
        self.assertEqual(parent["precondition_conditions"][0]["status"],
                         "state_prerequisite_unmet")
        self.assertEqual(child["precondition_progress"][0]["guard_states"], ("H.allowance",))
        self.assertEqual(child["precondition_conditions"][0]["status"],
                         "precondition_established")

    def test_explicit_state_guard_error_identifier_is_not_misclassified_as_parameter_bound(self):
        evidence = {"consume(uint256)": {"read_states": ["H.allowance"],
            "effect_evidence": [{"guards": [{"source": "H.sol#12",
                "state_reads": ["H.allowance"],
                "expression": "require(allowance[owner][msg.sender] >= amount, ALLOWANCE_TOO_LOW)"}]}]}}
        replay = {"replay_status": "failed", "transactions": [{"index": 1,
            "function": "consume(uint256)", "arguments": [4], "status": "outer_revert",
            "property_error": "execution reverted: ALLOWANCE_TOO_LOW"}]}
        vector = feedback_vector(replay, action_evidence=evidence)
        self.assertEqual(vector["precondition_conditions"][0]["status"],
                         "state_prerequisite_unmet")

    def test_property_predicate_excerpt_is_preferred_to_source_location(self):
        source = "if (payout[i] > deposits[i]) return false;"
        self.assertEqual(_property_source_for_feedback({
            "property_source": "WalletHarness.sol#60",
            "property_predicate": source}), source)

    def test_boolean_change_alone_does_not_claim_directional_progress(self):
        parent = {"replay_status": "executable", "transactions": [{
            "status": "success", "target_property": True}]}
        child = {"replay_status": "executable", "transactions": [{
            "status": "success", "target_property": True,
            "changed_predicate_getters": ["flag()"]}]}
        parent_vector = feedback_vector(parent, property_source="return invariant()")
        child_vector = feedback_vector(child, property_source="return invariant()",
                                       parent_vector=parent_vector)
        self.assertEqual(child_vector["target_progress"]["status"],
                         "observed_safe_no_directional_progress")

    def test_repeated_writer_is_only_proposed_for_evidenced_failed_guard(self):
        configure = {"function": "configure(uint256)", "arguments": [1],
                     "sender": SENDER, "value_wei": "0"}
        consume = {"function": "consume(uint256)", "arguments": [3],
                   "sender": SENDER, "value_wei": "0"}
        sequence = [configure, consume]
        templates = [configure]
        evidence = {
            "configure(uint256)": {"write_states": ["H.limit"]},
            "consume(uint256)": {"read_states": ["H.limit"], "effect_evidence": [{
                "guards": [{"source": "H.sol#12", "state_reads": ["H.limit"]}]}]},
        }
        abi = {"configure(uint256)": {"inputs": [{"name": "limit", "type": "uint256"}]},
               "consume(uint256)": {"inputs": [{"name": "amount", "type": "uint256"}]}}
        replay = {"transactions": [
            {"function": "configure(uint256)", "status": "success"},
            {"index": 2, "function": "consume(uint256)", "status": "outer_revert",
             "revert_reason": "insufficient allowance"}]}
        legacy = propose_extensions(sequence, templates, evidence, abi, mode="state_feedback",
                                    replay=replay, max_sequence_length=5, max_proposals=8)
        guided = propose_extensions(sequence, templates, evidence, abi, mode="state_feedback",
                                    replay=replay, max_sequence_length=5, max_proposals=8,
                                    allow_repeated_prerequisite=True)
        self.assertFalse(legacy)
        self.assertTrue(any(row["operator"] == "evidence_backed_repeated_prerequisite_insertion"
                            for row in guided))
        self.assertTrue(all(len(row["sequence"]) <= 5 for row in guided))

    def test_target_guidance_prefers_progress_and_keeps_unknown_candidates(self):
        legacy_best = {"sequence": [{"function": "cover()"}], "feedback": {
            "replay_complete": True, "property_related_state_changed": True,
            "target_progress": {"status": "observed_safe_no_directional_progress"},
            "transactions_succeeded": 1}}
        target_best = {"sequence": [{"function": "progress()"}], "feedback": {
            "replay_complete": True, "property_related_state_changed": False,
            "target_progress": {"status": "directional_progress"},
            "transactions_succeeded": 1}}
        self.assertIs(retain_diverse_prefixes([legacy_best.copy(), target_best.copy()], 1)[0]["sequence"][0]["function"],
                      "cover()")
        self.assertEqual(retain_diverse_prefixes([legacy_best.copy(), target_best.copy()], 1,
                                                 target_state_guided=True)[0]["sequence"][0]["function"],
                         "progress()")
        unknown = {"sequence": [{"function": "unknown()"}], "feedback": {
            "replay_complete": False, "target_progress": {"status": "unknown"},
            "transactions_succeeded": 0}}
        self.assertEqual(len(retain_diverse_prefixes([unknown], 1,
                                                     target_state_guided=True)), 1)


if __name__ == "__main__":
    unittest.main()
