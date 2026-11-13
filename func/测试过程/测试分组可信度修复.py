#!/usr/bin/env python3
"""回归检查：属性记录局部恢复、共享前缀、种子 ID 与失败语料保护。"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "func/功能"),
               str(ROOT / "deepseek/实验过程")]

from AgentA import normalize_agent_a_response  # noqa: E402
from AgentB import SENDERS, _validator  # noqa: E402
from 分组可信度修复实验 import _classify_campaign  # noqa: E402
from 种子验证 import _observed_effect_status, new_seed_id, write_corpus  # noqa: E402


P1, P2 = "property-one", "property-two"
MINT = "mint(uint256)"
BURN = "burn(uint256)"


def context_for_test() -> dict:
    return {"project": "UnitTest", "properties": [
        {"property_id": property_id, "property": property_id + ".echidna_ok()",
         "candidate_actions": [
             {"abi_signature": MINT, "abi_inputs": [{"name": "amount", "type": "uint256"}],
              "seed_compatible": True, "payable": False},
             {"abi_signature": BURN, "abi_inputs": [{"name": "id", "type": "uint256"}],
              "seed_compatible": True, "payable": False},
         ]}
        for property_id in (P1, P2)]}


class CredibilityRepairTests(unittest.TestCase):
    def test_invalid_agent_a_rows_do_not_discard_valid_group_candidates(self):
        context = context_for_test()
        response = {"property_sequences": [
            {"property_id": P1, "candidate_id": "one", "steps": [{"function": MINT}, {"function": BURN}]},
            {"property_id": "unknown", "candidate_id": "bad", "steps": [{"function": MINT}]},
            {"property_id": P2, "candidate_id": "bad-step", "steps": ["not-an-object"]},
            {"property_id": P2, "candidate_id": "two", "steps": [{"function": MINT}, {"function": BURN}]},
        ], "shared_prefixes": [{"property_ids": [P1, P2], "prefix_id": "common",
                               "steps": [{"function": MINT}]}]}
        result = normalize_agent_a_response(context, response, max_candidates=1,
                                            max_steps=4, min_steps=2)
        self.assertEqual({row["property_id"] for row in result["property_sequences"]}, {P1, P2})
        self.assertEqual(len(result["invalid_records"]), 2)
        self.assertEqual(len(result["applied_shared_prefixes"]), 2)
        self.assertEqual([row["steps"][0]["function"] for row in result["property_sequences"]],
                         [MINT, MINT])

    def test_shared_prefix_can_be_disabled_without_losing_valid_rows(self):
        context = context_for_test()
        response = {"property_sequences": [
            {"property_id": P1, "candidate_id": "one", "steps": [{"function": MINT}, {"function": BURN}]}
        ], "shared_prefixes": [{"property_ids": [P1, P2], "steps": [{"function": MINT}]}]}
        result = normalize_agent_a_response(context, response, max_candidates=1,
                                            max_steps=4, min_steps=2,
                                            use_shared_prefixes=False)
        self.assertEqual(len(result["property_sequences"]), 1)
        self.assertEqual(result["shared_prefixes"], [])
        self.assertFalse(result["property_sequences"][0].get("shared_prefix_id"))

    def test_agent_b_must_preserve_instantiated_shared_prefix(self):
        context = context_for_test()
        candidate = {"property_id": P1, "candidate_id": "candidate-1",
                     "steps": [{"function": MINT}, {"function": BURN}]}
        fixed = [{"function": MINT, "arguments": [5], "sender": SENDERS[0],
                  "value_wei": "0", "delay_seconds": 0, "delay_blocks": 0}]
        valid = {"property_id": P1, "candidate_id": "candidate-1", "transactions": [
            {**fixed[0]},
            {"function": BURN, "arguments": [0], "sender": SENDERS[0],
             "value_wei": "0", "delay_seconds": 0, "delay_blocks": 0},
        ]}
        _validator(context, candidate, None, fixed)(valid)
        mutated = json.loads(json.dumps(valid))
        mutated["transactions"][0]["arguments"] = [6]
        with self.assertRaises(ValueError):
            _validator(context, candidate, None, fixed)(mutated)

    def test_only_executable_replays_can_enter_corpus_and_seed_ids_are_unique(self):
        candidate = {"property_id": P1, "candidate_id": "same-candidate",
                     "steps": [{"function": MINT}]}
        context = context_for_test()
        txs = [{"function": MINT, "arguments": [1], "sender": SENDERS[0],
                "value_wei": "0", "delay_seconds": 0, "delay_blocks": 0}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                write_corpus("Request", candidate, txs, context, root,
                             replay={"replay_status": "replay_failed"}, seed_id=new_seed_id())
            self.assertFalse(root.exists() and any(root.rglob("*.txt")))
            first_id, second_id = new_seed_id(), new_seed_id()
            self.assertNotEqual(first_id, second_id)
            first = write_corpus("Request", candidate, txs, context, root,
                                 replay={"replay_status": "executable"}, seed_id=first_id)
            second = write_corpus("Request", candidate, txs, context, root,
                                  replay={"replay_status": "executable"}, seed_id=second_id)
            self.assertNotEqual(first, second)
            self.assertTrue(first.is_file() and second.is_file())
            with self.assertRaises(FileExistsError):
                write_corpus("Request", candidate, txs, context, root / "other-corpus",
                             replay={"replay_status": "executable"}, seed_id=first_id)
            self.assertEqual(json.loads(first.read_text(encoding="utf-8"))[0]["dst"].lower(),
                             "0xa647ff3c36cfab592509e13860ab8c4f28781a66")

    def test_initial_failure_is_attributed_separately(self):
        initial = {"property_failures": ["echidna_x: failed with no transactions made ⁉️"]}
        _classify_campaign(initial, "echidna_x", None)
        self.assertEqual(initial["failure_discovery_attribution"], "initial_state")
        self.assertTrue(initial["initial_state_failure"])

    def test_seed_replay_failure_is_not_attributed_to_fuzzing(self):
        campaign = {"property_failures": ["echidna_x: failed!"]}
        row = {"replay": {"target_property_violation": {"transaction_index": 2}}}
        _classify_campaign(campaign, "echidna_x", row)
        self.assertEqual(campaign["failure_discovery_attribution"], "prevalidated_seed")
        self.assertFalse(campaign["non_initial_failures_not_prevalidated"])

    def test_swallowed_internal_revert_is_detected_when_expected_getter_is_unchanged(self):
        context = context_for_test()
        action = context["properties"][0]["candidate_actions"][0]
        action["effect_evidence"] = [{"state": "TestToken.totalSupply"}]
        before = {"view_values": {"0x123:totalSupply()": 10}}
        after_changed = {"view_values": {"0x123:totalSupply()": 15}}
        after_unchanged = {"view_values": {"0x123:totalSupply()": 10}}
        after_unobservable = {"view_values": {"0x123:balanceOf(address)": 15}}
        self.assertEqual(_observed_effect_status(context, P1, MINT, before, after_changed)["status"],
                         "changed")
        self.assertEqual(_observed_effect_status(context, P1, MINT, before, after_unchanged)["status"],
                         "not_observed")
        self.assertEqual(_observed_effect_status(context, P1, MINT, before, after_unobservable)["status"],
                         "unknown")


if __name__ == "__main__":
    unittest.main(verbosity=2)
