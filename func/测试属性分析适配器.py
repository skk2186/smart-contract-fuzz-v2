#!/usr/bin/env python3
"""属性分析适配器的关系正确性和真实项目静态分析回归。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from crytic_compile import CryticCompile
from slither import Slither

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "func"))
from 属性分析适配器 import (  # noqa: E402
    PropertyAdapter, _build_compile_kwargs, _framework_root,
)


def property_named(report: dict, suffix: str) -> dict:
    return next(prop for prop in report["properties"]
                if prop["property"].endswith(suffix + "()"))


def action_named(property_report: dict, suffix: str) -> dict:
    return next(action for action in property_report["cross_contract"]["candidate_actions"]
                if action["function"].split(".", 1)[-1].startswith(suffix + "("))


class InstanceAndEvidenceRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["SOLC_VERSION"] = "0.8.20"
        cls.source = ROOT / "sol/属性分析回归样本.sol"
        cls.slither = Slither(CryticCompile(str(cls.source), skip_clean=True))
        cls.contract = next(c for c in cls.slither.contracts if c.name == "RegressionHarness")

    @classmethod
    def new_adapter(cls) -> PropertyAdapter:
        return PropertyAdapter(cls.slither, cls.contract, str(cls.source), None, None,
                               [], "echidna_", 12, 3, 1000)

    def test_two_instances_never_become_same_runtime_object_by_definition(self) -> None:
        report = self.new_adapter().run()
        alpha = property_named(report, "echidna_alpha_bound")
        beta = property_named(report, "echidna_beta_bound")
        for prop, direct, other in ((alpha, "setAlpha", "setBeta"),
                                    (beta, "setBeta", "setAlpha")):
            same = action_named(prop, direct)
            possible = action_named(prop, other)
            self.assertEqual(same["status"], "confirmed_static_path_candidate")
            self.assertEqual(possible["status"], "possible_instance_alias_candidate")
            self.assertEqual(same["matched_observations"][0]["relation"],
                             "confirmed_static_path")
            self.assertEqual(possible["matched_observations"][0]["relation"],
                             "possible_instance_alias")
            self.assertFalse(same["matched_observations"][0]["runtime_object_proven"])
            self.assertFalse(possible["matched_observations"][0]["runtime_object_proven"])
            self.assertNotEqual(same["matched_observations"][0]["action_receiver_path"],
                                possible["matched_observations"][0]["action_receiver_path"])

    def test_modifier_and_cfg_have_separate_write_site_evidence(self) -> None:
        report = self.new_adapter().run()
        prop = property_named(report, "echidna_alpha_bound")
        action = action_named(prop, "setAlpha")
        effects = [report["effect_catalog"][effect_id] for effect_id in action["effect_ids"]]
        self.assertEqual(len(effects), 2)
        self.assertEqual({guard["branch"] for effect in effects
                          for guard in effect["guards"]
                          if guard["kind"] == "control_branch"}, {"true", "false"})
        for effect in effects:
            self.assertTrue(any("onlyOwner" in guard["function"]
                                and "msg.sender" in guard["expression"]
                                for guard in effect["guards"]))
            self.assertTrue(effect["source"].endswith(("#20", "#22")))

    def test_dynamic_call_keeps_source_and_unknown_relation(self) -> None:
        report = self.new_adapter().run()
        prop = property_named(report, "echidna_alpha_bound")
        opaque = next(item for item in prop["cross_contract"]["opaque_call_candidates"]
                      if "callDynamic" in item["function"])
        self.assertEqual(opaque["status"], "opaque_effect_possible_no_property_link")
        self.assertTrue(any("LOW_LEVEL_CALL" in call["call"] and "#" in call["source"]
                            for call in opaque["calls"]))
        self.assertEqual(prop["analysis_status"], "analyzed")
        self.assertEqual(prop["context_status"], "candidate_with_write_site")

    def test_one_property_exception_does_not_erase_other_properties(self) -> None:
        adapter = self.new_adapter()
        real = adapter.analyze_property

        def analyze(prop):
            if prop.name == "echidna_alpha_bound":
                adapter.unknowns.add("该属性单独产生的未知项")
                raise RuntimeError("injected property failure")
            return real(prop)

        with patch.object(adapter, "analyze_property", side_effect=analyze):
            report = adapter.run()
        failed = property_named(report, "echidna_alpha_bound")
        other = property_named(report, "echidna_beta_bound")
        self.assertEqual(failed["analysis_status"], "partial")
        self.assertEqual(failed["dependency_status"], "unknown")
        self.assertTrue(failed["read_sites"] and failed["call_sites"])
        self.assertEqual(failed["evidence_ids"], [])
        self.assertTrue(any("该属性单独" in item for item in failed["unknowns"]))
        self.assertEqual(other["analysis_status"], "analyzed")
        self.assertFalse(any("该属性单独" in item for item in other["unknowns"]))
        self.assertEqual(set(report["effect_catalog"]), {
            effect_id for prop in report["properties"]
            for effect_id in prop["evidence_ids"]})

    def test_framework_detection_and_structured_cli_failures(self) -> None:
        with tempfile.TemporaryDirectory(prefix="adapter-framework-") as temp:
            base = Path(temp)
            for framework, config in (("Foundry", "foundry.toml"),
                                      ("Hardhat", "hardhat.config.js")):
                project = base / framework
                source = project / "contracts/Token.sol"
                source.parent.mkdir(parents=True)
                source.write_text("pragma solidity ^0.8.20; contract Token {}",
                                  encoding="utf-8")
                (project / config).write_text("", encoding="utf-8")
                root, detected = _framework_root(str(source))
                self.assertEqual((root, detected), (str(project), framework))

            output = base / "missing.json"
            run = subprocess.run(
                [sys.executable, str(ROOT / "func/属性分析适配器.py"),
                 str(base / "missing.sol"), "--output", str(output)],
                cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(report["execution_status"], "failed")
            self.assertTrue(report["errors"][0]["message"])

            output = base / "no_property.json"
            run = subprocess.run(
                [sys.executable, str(ROOT / "func/属性分析适配器.py"),
                 str(self.source), "--contract", "RegressionVault",
                 "--output", str(output)],
                cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
                env={**os.environ, "SOLC_VERSION": "0.8.20"})
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(run.returncode, 0)
            self.assertEqual(report["status"], "no_matching_property")
            self.assertTrue(report["contracts_discovered"])

    def test_compile_option_booleans_are_real_booleans(self) -> None:
        options = SimpleNamespace(solc_remaps=None, solc=None,
                                  compile_option=["foundry_compile_all=false",
                                                  "npx_disable=true", "solc_version=0.8.20"])
        kwargs = _build_compile_kwargs(options)
        self.assertIs(kwargs["foundry_compile_all"], False)
        self.assertIs(kwargs["npx_disable"], True)
        self.assertEqual(kwargs["solc_version"], "0.8.20")

    def test_inherited_property_has_distinct_context_identity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="adapter-inheritance-") as temporary:
            source = Path(temporary) / "inherited.sol"
            source.write_text(
                self.source.read_text(encoding="utf-8")
                + "\ncontract RegressionHarnessChild is RegressionHarness {}\n",
                encoding="utf-8")
            slither = Slither(CryticCompile(str(source), skip_clean=True))
            reports = {}
            for contract in slither.contracts:
                if contract.name in {"RegressionHarness", "RegressionHarnessChild"}:
                    adapter = PropertyAdapter(slither, contract, str(source), None, None,
                                              [], "echidna_", 12, 3, 1000)
                    reports[contract.name] = property_named(
                        adapter.run(), "echidna_alpha_bound")
            parent = reports["RegressionHarness"]
            child = reports["RegressionHarnessChild"]
            self.assertEqual(parent["property"], child["property"])
            self.assertNotEqual(parent["property_id"], child["property_id"])
            self.assertNotEqual(parent["analysis_contract"], child["analysis_contract"])

    def test_foundry_project_discovers_test_properties_and_keeps_compile_errors(self) -> None:
        forge = ROOT / ".tools/foundry/bin/forge"
        if not forge.is_file():
            self.skipTest("本地未安装 forge")
        with tempfile.TemporaryDirectory(prefix="adapter-foundry-native-") as temporary:
            project = Path(temporary)
            (project / "foundry.toml").write_text(
                "[profile.default]\nsrc = 'src'\ntest = 'test'\nout = 'out'\n",
                encoding="utf-8")
            (project / "src").mkdir()
            tests = project / "test"
            tests.mkdir()
            (tests / "good.sol").write_bytes(self.source.read_bytes())
            (tests / "bad.sol").write_text(
                "pragma solidity ^0.8.20; contract Broken { "
                "function echidna_bad() public returns (bool) { return missing; } }",
                encoding="utf-8")
            output = project / "analysis.json"
            env = {**os.environ, "PATH": f"{forge.parent}:{os.environ['PATH']}"}
            run = subprocess.run(
                [sys.executable, str(ROOT / "func/属性分析适配器.py"),
                 str(project), "--output", str(output)],
                cwd=ROOT, env=env, capture_output=True, text=True,
                timeout=120, check=False)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(run.returncode, 1)
            self.assertEqual(report["execution_status"], "partial")
            self.assertEqual(report["status"], "partial")
            self.assertEqual(report["input"]["foundry_target_mode"], "property_sources")
            self.assertEqual(len(report["input"]["analysis_targets"]), 2)
            self.assertEqual(len(report["properties"]), 3)
            self.assertEqual(len(report["source_issues"]), 1)
            self.assertTrue(report["source_issues"][0]["message"])
            self.assertIn("bad.sol", report["source_issues"][0]["target"])
            self.assertIn("missing", report["source_issues"][0]["compiler_log"])
            self.assertTrue(all(prop["analysis_status"] == "analyzed"
                                for prop in report["properties"]))


class RealProjectRegression(unittest.TestCase):
    """固定源码与关系语义断言，候选数量只用于发现意外空输出。"""

    PROJECTS = {
        "hokusai": ("sol/真实项目/Hokusai/contracts/echidna/EchidnaHokusaiToken.sol",
                    "@openzeppelin/contracts/=sol/真实项目/依赖/OpenZeppelin4/contracts/", None),
        "bee": ("sol/真实项目/BeeStorage/src/echidna/EchidnaSystemHarness.sol",
                "@openzeppelin/contracts/=sol/真实项目/依赖/OpenZeppelin482/contracts/", None),
        "request": ("sol/真实项目/Request/src/contracts/test/EchidnaERC20CommerceEscrowWrapper.sol",
                    "@openzeppelin/contracts/=sol/真实项目/依赖/OpenZeppelin4/contracts/", None),
        "kink": ("sol/真实项目/Kink/echidna/KinkPoolEchidna.sol",
                 "@openzeppelin/contracts/=sol/真实项目/依赖/OpenZeppelin550/contracts/",
                 "solc_args=--via-ir --optimize"),
        "opennfts": ("sol/真实项目/OpenNFTs/tests/echidna/OpenAutoMarketEx.e.sol",
                     "OpenNFTs/=sol/真实项目/OpenNFTs/", None),
        "immutable": ("sol/真实项目/Immutable/test/token/erc721/fuzz/ERC721PsiV2.Echidna.sol",
                      "openzeppelin-contracts-4/=sol/真实项目/依赖/OpenZeppelin4/contracts/ "
                      "openzeppelin-contracts-5/=sol/真实项目/依赖/OpenZeppelin561/contracts/", None),
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="property-regression-")
        cls.reports = {}
        env = os.environ.copy()
        env["SOLC_VERSION"] = "0.8.20"
        for project, (target, remaps, option) in cls.PROJECTS.items():
            output = Path(cls.temp.name) / f"{project}.json"
            command = [sys.executable, str(ROOT / "func/属性分析适配器.py"), target,
                       "--solc-remaps", remaps, "--output", str(output)]
            if option:
                command += ["--compile-option", option]
            completed = subprocess.run(command, cwd=ROOT, env=env,
                                       capture_output=True, text=True, timeout=120,
                                       check=False)
            if completed.returncode != 0:
                raise AssertionError(f"{project} 分析失败: {completed.stderr} {completed.stdout}")
            cls.reports[project] = json.loads(output.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_existing_five_and_independent_sixth_keep_property_evidence(self) -> None:
        expected = {"hokusai": 5, "bee": 4, "request": 16,
                    "kink": 4, "opennfts": 2, "immutable": 32}
        for project, count in expected.items():
            with self.subTest(project=project):
                report = self.reports[project]
                self.assertEqual(report["status"], "complete")
                self.assertEqual(report["execution_status"], "success")
                self.assertEqual(len(report["properties"]), count)
                self.assertTrue(all(prop["source"] != "unknown" and
                                    prop["analysis_status"] == "analyzed"
                                    for prop in report["properties"]))

    def test_relation_quality_across_projects(self) -> None:
        hokusai = property_named(self.reports["hokusai"], "echidna_investor_cap")
        self.assertTrue(any(c["status"] == "confirmed_static_path_candidate"
                            for c in hokusai["cross_contract"]["candidate_actions"]))

        bee = property_named(self.reports["bee"],
                             "echidna_stamp_internal_pot_not_above_contract_balance")
        self.assertEqual(bee["context_status"], "observations_only")
        self.assertTrue(bee["cross_contract"]["unmatched_observations"])
        self.assertTrue(any(c["calls"] for c in bee["cross_contract"]["opaque_call_candidates"]))

        request = property_named(self.reports["request"], "echidna_operator_authorization_enforced")
        self.assertTrue(request["candidate_actions"])
        self.assertTrue(request["cross_contract"]["observations"])

        kink = property_named(self.reports["kink"], "echidna_token0_accounting")
        self.assertTrue(kink["cross_contract"]["candidate_actions"])
        self.assertTrue(all(c["status"] != "confirmed_static_path_candidate"
                            for c in kink["cross_contract"]["candidate_actions"]))
        self.assertTrue(kink["cross_contract"]["alias_unproven_observations"])

        opennfts = property_named(self.reports["opennfts"], "echidna_owner")
        self.assertTrue(opennfts["evidence_summary"]["links_with_write_site"])

        immutable = property_named(self.reports["immutable"], "echidna_total_supply_matches")
        self.assertTrue(immutable["candidate_actions"])
        self.assertTrue(immutable["read_sites"])
        self.assertTrue(any(prop["property_write_states"]
                            for prop in self.reports["immutable"]["properties"]))

    def test_all_real_project_evidence_and_static_paths_are_consistent(self) -> None:
        for project, report in self.reports.items():
            with self.subTest(project=project):
                evidence = report["effect_catalog"]
                self.assertEqual(len({prop["property_id"] for prop in report["properties"]}),
                                 len(report["properties"]))
                for prop in report["properties"]:
                    self.assertTrue(set(prop["evidence_ids"]).issubset(evidence))
                    for candidate in (prop["candidate_actions"]
                                      + prop["cross_contract"]["candidate_actions"]):
                        self.assertTrue(set(candidate["effect_ids"]).issubset(evidence))
                    for candidate in prop["cross_contract"]["candidate_actions"]:
                        for match in candidate["matched_observations"]:
                            self.assertFalse(match["runtime_object_proven"])
                            if match["relation"] == "confirmed_static_path":
                                self.assertIsNotNone(match["action_receiver_path"])
                                self.assertEqual(match["action_receiver_path"],
                                                 match["observation_receiver_path"])

    def test_immutable_effect_ids_are_stable_across_processes(self) -> None:
        target, remaps, _ = self.PROJECTS["immutable"]
        output = Path(self.temp.name) / "immutable-repeat.json"
        run = subprocess.run(
            [sys.executable, str(ROOT / "func/属性分析适配器.py"), target,
             "--solc-remaps", remaps, "--output", str(output)],
            cwd=ROOT, env={**os.environ, "SOLC_VERSION": "0.8.20"},
            capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(run.returncode, 0, run.stderr)
        before = self.reports["immutable"]
        after = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(set(before["effect_catalog"]), set(after["effect_catalog"]))
        previous = {prop["property_id"]: prop for prop in before["properties"]}
        for prop in after["properties"]:
            self.assertEqual(prop["evidence_ids"],
                             previous[prop["property_id"]]["evidence_ids"])


if __name__ == "__main__":
    unittest.main()
