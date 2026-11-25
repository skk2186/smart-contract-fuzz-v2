#!/usr/bin/env python3
"""Olympia-independent tests for bounded dynamic-integer-array extension."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "func/功能"))
sys.path.insert(0, str(ROOT / "func/测试过程/跨交易属性状态依赖审计"))

from 状态反馈序列扩展 import (  # noqa: E402
    _dynamic_array_variants,
    _feedback_integer_hints,
    _value_fits,
    build_action_templates,
    propose_extensions,
    sequence_fingerprint,
)
from 真实合约统一执行适配器 import fixed_echidna_corpus  # noqa: E402
from Phase43批量实验 import parse_echidna_log  # noqa: E402


class DynamicArrayExtensionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.signature = "update(int8[])"
        self.abi = {self.signature: {"inputs": [{"name": "values", "type": "int8[]"}],
                                    "stateMutability": "nonpayable"}}
        self.sender = "0x0000000000000000000000000000000000010000"

    def transaction(self, values: list[int]) -> dict:
        return {"function": self.signature, "arguments": [values], "sender": self.sender,
                "value_wei": "0", "delay_seconds": 0, "delay_blocks": 0}

    def test_dynamic_signed_and_unsigned_abi_ranges(self) -> None:
        self.assertTrue(_value_fits("int8[]", [-128, 0, 127]))
        self.assertTrue(_value_fits("uint8[]", [0, 255]))
        self.assertTrue(_value_fits("int[]", [-(2 ** 255), 2 ** 255 - 1]))
        self.assertFalse(_value_fits("int8[]", [-129]))
        self.assertFalse(_value_fits("int8[]", [128]))
        self.assertFalse(_value_fits("uint8[]", [-1]))
        self.assertFalse(_value_fits("uint8[]", [256]))
        self.assertFalse(_value_fits("int8[]", [True]))
        self.assertFalse(_value_fits("int8[]", "1,2"))

    def test_action_template_uses_existing_array_or_safe_zero(self) -> None:
        action = {"abi_signature": self.signature, "analysis_status": "supported",
                  "seed_compatible": True, "matched_states": ["state"],
                  "read_states": [], "write_states": ["state"]}
        existing = self.transaction([6, -2])
        templates, decisions = build_action_templates(
            [action], self.abi, [existing], [self.sender])
        self.assertEqual(templates[0]["arguments"], [[6, -2]])
        self.assertEqual(decisions[0]["decision"], "template_created")

        templates, _ = build_action_templates([action], self.abi, [], [self.sender])
        self.assertEqual(templates[0]["arguments"], [[0]])

    def test_array_candidates_use_feedback_and_remain_in_abi_range(self) -> None:
        sequence = [self.transaction([0])]
        replay = {"transactions": [{"status": "success",
                                    "observations_after": {"observedCounter": 9}}]}
        candidates = propose_extensions(sequence, [], {}, self.abi, mode="state_feedback",
                                        replay=replay, max_sequence_length=1,
                                        max_proposals=24, random_seed=7)
        self.assertTrue(candidates)
        self.assertTrue(all(len(row["sequence"]) <= 1 for row in candidates))
        self.assertTrue(all(_value_fits("int8[]", row["sequence"][0]["arguments"][0])
                            for row in candidates))
        self.assertTrue(any(row["evidence"].get("value_source") == "observed_execution_state"
                            for row in candidates))
        fingerprints = [sequence_fingerprint(row["sequence"]) for row in candidates]
        self.assertEqual(len(fingerprints), len(set(fingerprints)))

    def test_failure_feedback_can_supply_a_minimum_array_length(self) -> None:
        replay = {"transactions": [{"status": "outer_revert",
                                    "revert_reason": "array length must be at least 4"}]}
        hints, required = _feedback_integer_hints(replay)
        self.assertEqual(required, 4)
        variants = _dynamic_array_variants("int8[]", [5], [], hints, required)
        self.assertTrue(any(values == [5, 0, 0, 0] and
                            "execution failure feedback" in reason
                            for values, reason, _ in variants))

    def test_copies_array_transactions_and_honors_proposal_budgets(self) -> None:
        sequence = [self.transaction([0])]
        candidates = propose_extensions(sequence, [], {}, self.abi, mode="state_feedback",
                                        replay=None, max_sequence_length=2,
                                        max_proposals=8, random_seed=11)
        self.assertLessEqual(len(candidates), 8)
        self.assertTrue(any(row["operator"] == "dynamic_array_transaction_copy"
                            for row in candidates))
        fingerprints = [sequence_fingerprint(row["sequence"]) for row in candidates]
        self.assertEqual(len(fingerprints), len(set(fingerprints)))
        capped = propose_extensions(sequence, [], {}, self.abi, mode="state_feedback",
                                    replay=None, max_sequence_length=1,
                                    max_proposals=2, random_seed=11)
        self.assertLessEqual(len(capped), 2)
        self.assertTrue(all(len(row["sequence"]) <= 1 for row in capped))

    def test_candidate_values_can_be_copied_from_existing_valid_array_parameters(self) -> None:
        sequence = [self.transaction([-7, 11]), self.transaction([0])]
        candidates = propose_extensions(sequence, [], {}, self.abi, mode="state_feedback",
                                        replay=None, max_sequence_length=2,
                                        max_proposals=100, random_seed=19)
        copied_value = [row for row in candidates
                        if row.get("evidence", {}).get("value_source") ==
                        "copied from a valid sequence array element"]
        self.assertTrue(copied_value)
        self.assertTrue(any(row["sequence"][1]["arguments"] == [[-7]]
                            for row in copied_value))
        self.assertTrue(all(_value_fits("int8[]", tx["arguments"][0])
                            for row in candidates for tx in row["sequence"]))

    def test_echidna_corpus_encodes_signed_and_unsigned_dynamic_arrays(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sequence = {"transactions": [{
                "signature": "consume(int8[],uint256[])",
                "arguments": [[-3, 2], [7, 2 ** 256 - 1]],
                "sender": self.sender,
                "value_wei": "0",
            }]}
            seed_path = fixed_echidna_corpus(sequence, "0x" + "22" * 20, Path(directory))
            encoded = json.loads(seed_path.read_text(encoding="utf-8"))[0]
            args = encoded["call"]["contents"][1]
            self.assertEqual(args[0]["tag"], "AbiArrayDynamic")
            self.assertEqual(args[0]["contents"][0], {"tag": "AbiIntType", "contents": 8})
            self.assertEqual(args[0]["contents"][1][0]["contents"], [8, "-3"])
            self.assertEqual(args[1]["tag"], "AbiArrayDynamic")
            self.assertEqual(args[1]["contents"][0], {"tag": "AbiUIntType", "contents": 256})
            self.assertEqual(args[1]["contents"][1][-1]["contents"], [256, str(2 ** 256 - 1)])

    def test_echidna_corpus_rejects_out_of_range_array_elements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sequence = {"transactions": [{
                "signature": "consume(int8[])", "arguments": [[128]],
                "sender": self.sender, "value_wei": "0",
            }]}
            with self.assertRaisesRegex(ValueError, "outside ABI range"):
                fixed_echidna_corpus(sequence, "0x" + "22" * 20, Path(directory))

    def test_echidna_final_failed_line_with_worker_falsified_marker_is_counterexample(self) -> None:
        log = "[Worker 0] Test echidna_noBug falsified!\n" \
              "echidna_noBug: failed!\nUnique instructions: 12"
        result = parse_echidna_log(log, 1.25, 1, False)
        self.assertEqual(result["target_property_status"], "falsified")
        self.assertTrue(result["native_counterexample"])
        self.assertEqual(result["status"], "native_counterexample")
        self.assertEqual(result["time_to_first_native_counterexample_seconds"], 1.25)

    @unittest.skipUnless(os.environ.get("PHASE44_RUN_ECHIDNA") == "1",
                         "set PHASE44_RUN_ECHIDNA=1 for native Echidna corpus replay")
    def test_native_echidna_replays_non_olympia_array_corpus(self) -> None:
        echidna = shutil.which("echidna") or "/usr/local/bin/echidna"
        harness = ROOT / "sol/单合约测试/动态数组序列扩展测试/ArraySequenceHarness.sol"
        sequence = {"transactions": [{
            "signature": "consume(int8[],uint256[])",
            "arguments": [[-3, 2], [7]], "sender": self.sender, "value_wei": "0",
        }]}
        env = os.environ.copy()
        tool_root = Path("/home/skk/smart-contract-fuzz-v2/.tools")
        env["PYTHONPATH"] = ":".join([
            str(tool_root / "phase43-runtime-py311"), str(ROOT / "deepseek"),
            str(ROOT / "func/功能"), env.get("PYTHONPATH", "")]).rstrip(":")
        env["SOLCX_BINARY_PATH"] = str(tool_root / "olympia-solc")
        env["PATH"] = ":".join([
            str(tool_root / "phase43-solc-bin"), str(tool_root / "olympia-venv/bin"),
            "/home/skk/.local/bin", str(tool_root / "phase43-z3-root/usr/bin"),
            "/usr/local/bin", "/usr/bin", env.get("PATH", "")])
        with tempfile.TemporaryDirectory() as directory:
            corpus_root = Path(directory) / "corpus"
            fixed_echidna_corpus(sequence, "0x00a329c0648769A73afAc7F9381E08FB43dBEA72",
                                 corpus_root)
            command = [echidna, str(harness), "--contract", "ArraySequenceHarness",
                       "--test-mode", "property", "--workers", "1", "--seq-len", "1",
                       "--test-limit", "0", "--seed", "44", "--shrink-limit", "1",
                       "--contract-addr", "0x00a329c0648769A73afAc7F9381E08FB43dBEA72",
                       "--deployer", "0x0000000000000000000000000000000000030000",
                       "--sender", self.sender, "--corpus-dir", str(corpus_root),
                       "--coverage-dir", str(corpus_root), "--disable-onchain-sources",
                       "--format", "text"]
            completed = subprocess.run(command, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True,
                                       encoding="utf-8", errors="replace", timeout=180,
                                       check=False)
            self.assertIn("Loaded 1 transaction sequences", completed.stdout)
            self.assertIn("Sequence replayed from corpus file", completed.stdout)
            self.assertRegex(completed.stdout, r"echidna_array_input_replays:\s*failed")


if __name__ == "__main__":
    unittest.main()
