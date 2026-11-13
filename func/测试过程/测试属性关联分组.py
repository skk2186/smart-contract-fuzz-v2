#!/usr/bin/env python3
"""属性分组的语义边界回归：上下文、实例别名和完全连接约束。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "func/功能"))

from 属性关联分组 import analyze


def prop(pid, states, action, contract="Harness", source="Harness.sol", possible=False):
    cross_actions = [{"function": "Target.write()", "effect_ids": ["e"],
                      "status": "possible_instance_alias_candidate"}] if possible else []
    observations = [{"receiver_path": ["Harness.target"], "read_states": ["Target.value"]}]
    return {
        "property_id": pid, "property": pid, "analysis_contract": contract,
        "analysis_contract_source": source, "read_states": states,
        "candidate_actions": [{"function": action, "effect_ids": ["e"]}] if action else [],
        "cross_contract": {"observations": observations if possible else [],
                           "candidate_actions": cross_actions},
        "prerequisite_state_closure": [],
    }


class GroupingTests(unittest.TestCase):
    def test_context_and_complete_link(self):
        report = {
            "effect_catalog": {str(i): {"state": s} for i, s in enumerate(
                ["Harness.a", "Harness.b", "Target.value"])},
            "properties": [
                prop("A", ["Harness.a"], "write()"),
                prop("B", ["Harness.a", "Harness.b"], "write()"),
                prop("C", ["Harness.b"], "write()"),
                prop("D", ["Harness.a"], "write()", source="Other.sol"),
                prop("E", [], None, possible=True),
                prop("F", [], None, possible=True),
            ],
        }
        result = analyze(report, trials=25, seed=42)
        groups = [set(member["property_id"] for member in g["members"])
                  for g in result["groups"]]
        self.assertEqual(set.union(*groups), {"A", "B", "C", "D", "E", "F"})
        self.assertEqual(sum(len(g) for g in groups), 6)
        self.assertTrue({"A", "B"} in groups or {"B", "C"} in groups)
        self.assertFalse(any({"A", "B", "C"} <= g for g in groups))
        self.assertTrue({"D"} in groups)
        self.assertTrue({"E"} in groups and {"F"} in groups)
        metric = result["evaluation"]
        self.assertEqual(metric["grouped"]["within_pairs"],
                         metric["matched_random"]["mean"]["within_pairs"])


if __name__ == "__main__":
    unittest.main()
