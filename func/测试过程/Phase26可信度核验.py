#!/usr/bin/env python3
"""冻结 Phase25 固定种子并分离 Echidna 回放、变异与最终覆盖口径。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "deepseek"))

from AgentB import HARNESS_ADDRESS, PROPERTY_SENDER, SENDERS  # noqa: E402
from func.功能 import 种子验证 as verifier  # noqa: E402

DEPLOYER = verifier.DEPLOYER


OUTPUT = ROOT / "deepseek/结果/Phase26研究主线与可信度核验-20261117-修订1"
PRIOR_OUTPUT = ROOT / "deepseek/结果/Phase26研究主线与可信度核验-20261117"
PHASE25 = ROOT / "deepseek/结果/Phase25跨交易状态约束参数修复-索引映射复验-20261117"
PHASE25_SUMMARY = PHASE25 / "Phase25原始汇总.json"
RANDOM_SEEDS = (20261125, 20261135, 20261145)
FUZZ_LIMIT = 500
REPLAY_LIMIT = 0
SEQ_LEN = 8
SHRINK_LIMIT = 1
TIMEOUT_SECONDS = 1800
SAMPLES = (
    "request_refund_quota",
    "immutable_mint_then_approve",
    "beestorage_batch_id_no_hint",
    "opennfts_reach_other_balance",
)
TREATMENTS = ("seed_only_replay", "empty_corpus_replay",
             "native_empty_corpus", "seeded_fuzz")

SOURCE_PATHS = (
    Path("AGENTS.md"),
    Path("docs/00_项目目录标准.md"),
    Path("docs/08_Echidna原生种子加载回放变异验证.md"),
    Path("docs/21_实验可信度与目标状态验证.md"),
    Path("docs/24_逐属性种子选择与持续探索验证.md"),
    Path("docs/25_跨交易状态约束与参数修复实验.md"),
    Path("func/功能/种子验证.py"),
    Path("func/功能/跨交易状态约束.py"),
    Path("func/测试过程/Phase26可信度核验.py"),
    Path("deepseek/AgentB.py"),
    Path("deepseek/结果/Phase25跨交易状态约束参数修复-索引映射复验-20261117/Phase25原始汇总.json"),
    Path("sol/真实项目/Request/src/contracts/test/EchidnaERC20CommerceEscrowWrapper.sol"),
    Path("sol/真实项目/Request/src/contracts/ERC20CommerceEscrowWrapper.sol"),
    Path("sol/真实项目/Immutable/test/token/erc721/fuzz/ERC721PsiV2.Echidna.sol"),
    Path("sol/真实项目/Immutable/contracts/token/erc721/erc721psi/ERC721PsiV2.sol"),
    Path("sol/真实项目/BeeStorage/src/echidna/EchidnaSystemHarness.sol"),
    Path("sol/真实项目/BeeStorage/src/PostageStamp.sol"),
    Path("sol/真实项目/OpenNFTs/tests/echidna/OpenAutoMarketEx.e.sol"),
    Path("sol/真实项目/OpenNFTs/tests/examples/OpenAutoMarketEx.sol"),
    Path("sol/真实项目/OpenNFTs/contracts/OpenERC/OpenERC721.sol"),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _binary_version(binary: str) -> str:
    result = subprocess.run([binary, "--version"], cwd=ROOT,
                            capture_output=True, text=True, check=True)
    return (result.stdout + result.stderr).strip()


def _load_phase25() -> dict[str, Any]:
    if not PHASE25_SUMMARY.is_file():
        raise FileNotFoundError(PHASE25_SUMMARY)
    return json.loads(PHASE25_SUMMARY.read_text(encoding="utf-8"))


def _current_hashes(phase25: dict[str, Any]) -> dict[str, str]:
    paths = list(SOURCE_PATHS)
    for sample in phase25["plan"]["samples"]:
        if sample["sample_id"] not in SAMPLES:
            continue
        for source in sample.get("source_records", []):
            path = Path(source["report"])
            if path not in paths:
                paths.append(path)
    return {path.as_posix(): sha256_file(ROOT / path)
            for path in sorted(paths, key=lambda p: p.as_posix())}


def _sample_rows(phase25: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["sample_id"]: row for row in phase25["plan"]["samples"]
            if row["sample_id"] in SAMPLES}


def freeze() -> dict[str, Any]:
    if OUTPUT.exists():
        raise FileExistsError(f"拒绝覆盖已有 Phase26 结果目录：{OUTPUT}")
    phase25 = _load_phase25()
    samples = _sample_rows(phase25)
    if set(samples) != set(SAMPLES):
        raise RuntimeError("Phase25 固定案例不完整，不能冻结 Phase26 复验")
    prior_seeds = {
        row["sample_id"]: row["seed_file"]
        for row in phase25["echidna_runs"]
        if row["treatment"] == "G1_valid_seed" and row["random_seed"] == RANDOM_SEEDS[0]
    }
    if set(prior_seeds) != set(SAMPLES):
        raise RuntimeError("Phase25 不是每个固定案例均有可复用的 Anvil 有效种子")
    input_files = {}
    source_record_hashes = {}
    for sample in phase25["plan"]["samples"]:
        if sample["sample_id"] not in SAMPLES:
            continue
        for source in sample.get("source_records", []):
            path = ROOT / source["report"]
            observed = sha256_file(path)
            if observed != source["report_sha256"]:
                raise RuntimeError(f"Phase25 种子来源报告哈希不符：{path}")
            source_record_hashes[path.relative_to(ROOT).as_posix()] = observed
    for sample_id, relpath in prior_seeds.items():
        path = ROOT / relpath
        if not path.is_file():
            raise FileNotFoundError(path)
        input_files[sample_id] = {"path": relpath, "sha256": sha256_file(path)}
    source_hashes = _current_hashes(phase25)
    report = {
        "phase": 26,
        "status": "frozen-before-phase26-revised-echidna-runs",
        "revision": 1,
        "supersedes_plan": {
            "path": (PRIOR_OUTPUT / "实验方案.json").relative_to(ROOT).as_posix(),
            "sha256": sha256_file(PRIOR_OUTPUT / "实验方案.json"),
            "failed_campaign_summary": (
                PRIOR_OUTPUT / "Phase26原始汇总.json").relative_to(ROOT).as_posix(),
            "failed_campaign_summary_sha256": sha256_file(
                PRIOR_OUTPUT / "Phase26原始汇总.json")},
        "operational_amendment": {
            "reason": "初版 48 个 campaign 均因 Echidna 2.3.2 输出 No contracts found in given file 而退出；在源码临时副本中移除 --export-dir 后可发现并分析 OpenNFT Harness。",
            "change": "正式矩阵改在每个项目的临时源码副本中运行，使用 Echidna 默认 crytic-export 位置；样本、随机种子、属性、预算、sender、编译配置、指标及成功口径不变。",
            "diagnostic_only_open_nft_test_limit_0_still_passing": True,
            "diagnostic_evidence_dir": (
                PRIOR_OUTPUT / "诊断证据/OpenNFTs-testLimit0-no-export").relative_to(ROOT).as_posix()},
        "frozen_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "baseline_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True).stdout.strip(),
        "objective": "对 Phase25 四个固定案例分离种子单独回放覆盖、500-test 后续新增覆盖和最终覆盖；查明 OpenNFTs corpus replay 与 Anvil 属性状态差异。",
        "research_freeze": {
            "mainline": [
                "安全属性分析",
                "Agent A/B 多交易规划及参数生成",
                "Anvil 实际执行反馈与跨交易参数修复",
                "有效种子验证",
                "Echidna 模糊测试"],
            "research_question": "在不修改 Harness、属性或真实项目合约的条件下，基于事件、getter、Slither 和真实失败结果的有界跨交易约束处理，能否提高独立项目上的有效序列/目标状态到达，并在相同 Echidna 预算下增加纯种子回放之外的新路径？",
            "method_modules": [
                "属性与 Slither 读取/写入/守卫分析",
                "Agent A/B 生成多交易计划和 ABI 参数",
                "Anvil 事件、返回值、getter、状态差和 revert 反馈",
                "有界对象键/额度修复并完整重放验证",
                "有效语料与 Echidna seed-only / fuzz / final 覆盖分离"],
            "candidate_contributions": [
                {"id": "C1", "claim": "通用的真实执行反馈约束解析，可沿事件对象键和可观察额度修复受影响参数，保留成功前缀并经全序列复验。", "status": "Phase25 诊断样本有可重复可行性证据，独立留出泛化待验证。"},
                {"id": "C2", "claim": "将种子回放状态、回放覆盖、后续变异新增覆盖和最终覆盖分开测量的可信因果验证协议。", "status": "Phase26 先完成固定案例口径核验，学术新颖性待与独立留出实验比较。"}],
            "known_failure_types": [
                "对象尚未创建或事件字段缺失/歧义/ABI 类型不兼容",
                "数值参数超过前序额度/余额，或 getter 无法观察到约束",
                "Slither 守卫只给出候选依赖，源码映射无法唯一解释",
                "外层调用成功但内部调用被 Harness 捕获并回滚",
                "角色/sender 与对象 owner/operator 不一致",
                "交易有存储变化但属性目标状态未到达",
                "RPC/编译/trace 错误导致证据不完整",
                "外部 corpus 被加载/回放，但目标属性末态未被该 replay 结果证明",
                "覆盖增加发生在种子回放还是后续 fuzz 阶段无法分离"],
            "next_stage_controls": {
                "G0": "同 Harness/属性/配置的 native Echidna，空语料，testLimit=500。",
                "G1": "同候选输入启用既有运行时约束机制；只注入 Anvil 完整重放有效的冻结种子，testLimit=500。",
                "G2": "同一候选序列关闭新增运行时约束修复；Anvil 失败不得伪装成有效种子，Echidna 对照仍运行并明确空语料状态。",
                "paired_repeats": 3,
                "random_seeds": list(RANDOM_SEEDS),
                "other_controls": "Harness、源码、属性、sender/deployer、solc/remappings、seqLen=8、workers=1、shrinkLimit=1、stopOnFail=false、disableSlither=true 完全相同。"},
            "next_stage_selection_rule": {
                "pool": "只从仓库中已经存在的真实项目 Harness/属性清单选取；不搜索或接入新基准。",
                "exclude": "排除 Phase10–25 已作为开发、诊断或回归输入的项目/属性，包括 Request、Immutable、BeeStorage、OpenNFTs 及既有 Hokusai/Kink 固定样本。",
                "eligibility_before_fuzz": "现有 Harness 可按仓库固定 compiler recipe 编译；部署时目标属性为真；Slither 静态信息显示至少两个外部 Harness 动作之间存在状态读写依赖。资格只用源码/部署前置状态判定，不看回放成功率、覆盖或 fuzz 结果。",
                "deterministic_order": "对每个合格项目/属性计算 SHA-256('phase27-independent-v1|' + canonical_project_path + '|' + property_signature)，按 digest 升序，每项目最多取首个属性，固定取前 6 个项目。",
                "no_replacement": "冻结后编译失败、Agent 无有效序列或 Anvil 失败的任务继续留在原位并计入失败；不换属性、不放宽条件、不按成功口径筛样。若合格项目少于 4 个，报告样本不足并停止正式泛化结论。",
                "generation_budget": "复用现有 Agent A/B；每个样本一次规划、一次 Agent B 候选、至多一次参数修复和一次受成功前缀约束的重规划；不增加 Agent 或重试。"}},
        "phase25_experiment_summary_sha256": sha256_file(PHASE25_SUMMARY),
        "sample_ids": list(SAMPLES),
        "input_seed_files": input_files,
        "treatments": {
            "seed_only_replay": {
                "test_limit": REPLAY_LIMIT,
                "corpus": "同一 Phase25 已验证种子，仅作初始外部 corpus",
                "purpose": "测量 Echidna 在 fuzz 测试数为 0 时回放该语料得到的覆盖和属性报告"},
            "empty_corpus_replay": {
                "test_limit": REPLAY_LIMIT,
                "corpus": "空外部 corpus",
                "purpose": "扣除零预算启动、部署与 worker 初始行为，报告种子回放相对空语料的新增行"},
            "native_empty_corpus": {
                "test_limit": FUZZ_LIMIT,
                "corpus": "空外部 corpus",
                "purpose": "同 Harness、同随机种子的 native 基线"},
            "seeded_fuzz": {
                "test_limit": FUZZ_LIMIT,
                "corpus": "同一 Phase25 已验证种子",
                "purpose": "报告最终覆盖；新增 LCOV 行为其最终命中行减 seed_only_replay 的命中行"}},
        "echidna_configuration": {
            "version": _binary_version(str(verifier.ECHIDNA_BIN)),
            "random_seeds": list(RANDOM_SEEDS),
            "test_limit": FUZZ_LIMIT,
            "seq_len": SEQ_LEN,
            "shrink_limit": SHRINK_LIMIT,
            "workers": 1,
            "stop_on_fail": False,
            "disable_slither": True,
            "test_mode": "property",
            "coverage": True,
            "timeout_seconds": TIMEOUT_SECONDS,
            "property_sender": PROPERTY_SENDER,
            "sender_pool": list(SENDERS),
            "deployer": DEPLOYER,
            "contract_address": HARNESS_ADDRESS,
            "max_gas_per_call": verifier.MAX_TX_GAS,
            "balance": verifier.INITIAL_BALANCE,
            "gas_price": 0,
            "solc_version": "0.8.20"},
        "same_configuration_assertions": [
            "native_empty_corpus 与 seeded_fuzz 的 testLimit、random seed、Harness、property、sender、deployer、compiler config、seqLen、shrinkLimit、worker、stopOnFail 相同；仅 corpusDir 与 corpus 内容不同。",
            "seed_only_replay 与 seeded_fuzz 使用相同随机种子、Harness、property、sender、deployer、compiler config、seqLen、shrinkLimit、worker、stopOnFail；testLimit 按测量目的分别为 0 与 500。"],
        "coverage_metrics": {
            "seed_only": "testLimit=0 外部语料 replay campaign 的 LCOV 命中源码行集合",
            "after_fuzz_new_lines": "seeded_fuzz 最终 LCOV 集合减 seed_only_replay LCOV 集合",
            "final": "seeded_fuzz campaign 最终 LCOV 行集合与 unique instructions",
            "native": "native_empty_corpus campaign 最终 LCOV 行集合与 unique instructions",
            "limitation": "LCOV 行差可精确计算；Echidna unique-instruction 数值为 campaign 汇总且不提供按 seed-only 与 fuzzing 阶段的精确拆分。"},
        "source_sha256": source_hashes,
        "seed_provenance_report_sha256": source_record_hashes,
        "seed_provenance": "完全复用 Phase25 冻结复验中 Anvil 已验证的四条种子；不调用模型、不修改 seed 内容、不根据 Phase26 结果换样。"}
    OUTPUT.mkdir(parents=True)
    write_json(OUTPUT / "实验方案.json", report)
    return report


def _lcov_hits(campaign: Path, source_root: Path) -> list[str]:
    files = list(campaign.glob("covered.*.lcov"))
    if len(files) != 1:
        return []
    source = ""
    hits = set()
    for line in files[0].read_text(encoding="utf-8").splitlines():
        if line.startswith("SF:"):
            raw = Path(line[3:])
            try:
                source = raw.relative_to(source_root).as_posix()
            except ValueError:
                try:
                    source = raw.relative_to(ROOT).as_posix()
                except ValueError:
                    source = str(raw)
        elif line.startswith("DA:"):
            line_number, count, *_ = line[3:].split(",")
            if int(count) > 0:
                hits.add(f"{source}:{int(line_number)}")
    return sorted(hits)


def _normalized_config(campaign: Path, project: str) -> dict[str, Any]:
    yaml_path = campaign.parent / f"{project}-{campaign.name}-echidna.yaml"
    compiler_path = campaign.parent / f"{project}-{campaign.name}-crytic-compile.json"
    yaml_text = yaml_path.read_text(encoding="utf-8")
    normalized_yaml = "\n".join(
        "corpusDir: <CORPUS>" if line.startswith("corpusDir: ") else line
        for line in yaml_text.splitlines())
    compiler = json.loads(compiler_path.read_text(encoding="utf-8"))
    return {"echidna_yaml_normalized": normalized_yaml,
            "crytic_compile": compiler,
            "echidna_yaml_sha256": sha256_file(yaml_path),
            "crytic_compile_sha256": sha256_file(compiler_path)}


def _load_existing(campaign: Path) -> dict[str, Any] | None:
    result_path = campaign / "campaign-result.json"
    if result_path.is_file():
        return json.loads(result_path.read_text(encoding="utf-8"))
    if campaign.exists():
        raise RuntimeError(f"发现不完整 campaign，拒绝覆盖：{campaign}")
    return None


def _assert_matched_configuration(native: dict[str, Any], replay: dict[str, Any],
                                  empty_replay: dict[str, Any],
                                  fuzzed: dict[str, Any], seed: int) -> None:
    reference = native["configuration"]
    for row in (replay, empty_replay, fuzzed):
        config = row["configuration"]
        if config["echidna_yaml_normalized"] != reference["echidna_yaml_normalized"]:
            raise RuntimeError("配对 Echidna YAML 除 corpusDir 外存在差异")
        if config["crytic_compile"] != reference["crytic_compile"]:
            raise RuntimeError("配对 Crytic Compile 配置不一致")
    expected_limits = {"native_empty_corpus": FUZZ_LIMIT,
                       "seed_only_replay": REPLAY_LIMIT,
                       "empty_corpus_replay": REPLAY_LIMIT,
                       "seeded_fuzz": FUZZ_LIMIT}
    for row in (native, replay, empty_replay, fuzzed):
        command = row["command"]
        if command[command.index("--test-limit") + 1] != str(expected_limits[row["treatment"]]):
            raise RuntimeError(f"Echidna testLimit 与冻结方案不一致：{row['treatment']}")
        if command[command.index("--seed") + 1] != str(seed):
            raise RuntimeError("Echidna random seed 与配对方案不一致")


def _run_campaign(sample: dict[str, Any], sample_id: str, treatment: str,
                  repetition_seed: int, seed_source: Path | None,
                  test_limit: int, source_root: Path) -> dict[str, Any]:
    campaign = (OUTPUT / "Echidna" / sample_id / str(repetition_seed) / treatment)
    existing = _load_existing(campaign)
    if existing is not None:
        return existing
    campaign.mkdir(parents=True, exist_ok=False)
    if seed_source is not None:
        coverage = campaign / "coverage"
        coverage.mkdir()
        shutil.copy2(seed_source, coverage / "coverage-seed.txt")
    property_name = sample["property"].rsplit(".", 1)[-1].split("(", 1)[0]
    wall_started = time.monotonic()
    result = verifier.run_echidna(
        sample["project"], campaign, property_name=property_name,
        test_limit=test_limit, timeout=TIMEOUT_SECONDS, seed=repetition_seed,
        seq_len=SEQ_LEN, shrink_limit=SHRINK_LIMIT, stop_on_fail=False,
        disable_slither=True, test_mode="property", property_prefix=property_name,
        sender_pool=SENDERS, working_directory=source_root)
    hit_lines = _lcov_hits(campaign, source_root)
    output = {
        "sample_id": sample_id,
        "project": sample["project"],
        "property": sample["property"],
        "treatment": treatment,
        "random_seed": repetition_seed,
        "test_limit": test_limit,
        "input_seed": seed_source.relative_to(ROOT).as_posix() if seed_source else None,
        "input_seed_sha256": sha256_file(seed_source) if seed_source else None,
        "status": result["status"],
        "exit_code": result["exit_code"],
        "loaded_seed_count": result["loaded_seed_count"],
        "replayed_sequence_count": result["replayed_sequence_count"],
        "external_seed_replayed": result["replay_evidence"],
        "mutation_evidence": result["mutation_evidence"],
        "fuzzing_transactions": result["fuzzing_transactions"],
        "fuzzing_cases": result["fuzzing_cases"],
        "unique_instructions": result["unique_instructions"],
        "coverage_source": result["coverage_source"],
        "lcov_path": next(campaign.glob("covered.*.lcov")).relative_to(ROOT).as_posix()
        if list(campaign.glob("covered.*.lcov")) else None,
        "lcov_hit_lines": hit_lines,
        "lcov_hit_line_count": len(hit_lines),
        "target_property_results": result["target_property_results"],
        "property_failures": result["property_failures"],
        "process_elapsed_seconds": result["elapsed_seconds"],
        "full_campaign_wall_seconds": round(time.monotonic() - wall_started, 6),
        "log_path": result["full_log_path"],
        "command": result["command"],
        "compiler_working_directory_kind": "temporary source mirror with default Echidna crytic-export",
        "configuration": _normalized_config(campaign, sample["project"])}
    write_json(campaign / "campaign-result.json", output)
    return output


def _copy_isolated_sources(project: str, source_root: Path) -> None:
    real_projects = source_root / "sol/真实项目"
    real_projects.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "sol/真实项目" / project,
                    real_projects / project)
    shutil.copytree(ROOT / "sol/真实项目/依赖",
                    real_projects / "依赖")


def run_frozen() -> dict[str, Any]:
    plan_path = OUTPUT / "实验方案.json"
    if not plan_path.is_file():
        raise FileNotFoundError(f"尚未冻结方案：{plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    phase25 = _load_phase25()
    current_hashes = _current_hashes(phase25)
    if plan.get("source_sha256") != current_hashes:
        raise RuntimeError("源码、Harness、报告或输入汇总与冻结哈希不符，拒绝运行")
    if plan.get("phase25_experiment_summary_sha256") != sha256_file(PHASE25_SUMMARY):
        raise RuntimeError("Phase25 汇总哈希与冻结方案不符")
    samples = _sample_rows(phase25)
    seeds = {sample_id: ROOT / row["path"]
             for sample_id, row in plan["input_seed_files"].items()}
    if set(seeds) != set(SAMPLES):
        raise RuntimeError("冻结输入种子清单不完整")
    for sample_id, path in seeds.items():
        if sha256_file(path) != plan["input_seed_files"][sample_id]["sha256"]:
            raise RuntimeError(f"Phase25 输入种子哈希不符：{sample_id}")
    campaigns = []
    for sample_id in SAMPLES:
        sample = samples[sample_id]
        with tempfile.TemporaryDirectory(prefix=f"phase26-{sample['project']}-") as temp:
            source_root = Path(temp)
            _copy_isolated_sources(sample["project"], source_root)
            for seed in RANDOM_SEEDS:
                replay = _run_campaign(sample, sample_id, "seed_only_replay",
                                       seed, seeds[sample_id], REPLAY_LIMIT, source_root)
                empty_replay = _run_campaign(sample, sample_id, "empty_corpus_replay",
                                             seed, None, REPLAY_LIMIT, source_root)
                native = _run_campaign(sample, sample_id, "native_empty_corpus",
                                       seed, None, FUZZ_LIMIT, source_root)
                fuzzed = _run_campaign(sample, sample_id, "seeded_fuzz",
                                       seed, seeds[sample_id], FUZZ_LIMIT, source_root)
                _assert_matched_configuration(native, replay, empty_replay, fuzzed, seed)
                replay_lines = set(replay["lcov_hit_lines"])
                empty_replay_lines = set(empty_replay["lcov_hit_lines"])
                final_lines = set(fuzzed["lcov_hit_lines"])
                fuzzed["seed_only_lcov_hit_line_count"] = len(replay_lines)
                fuzzed["seed_only_marginal_lcov_hit_lines"] = sorted(
                    replay_lines - empty_replay_lines)
                fuzzed["seed_only_marginal_lcov_hit_line_count"] = len(
                    replay_lines - empty_replay_lines)
                fuzzed["new_lcov_hit_lines"] = sorted(final_lines - replay_lines)
                fuzzed["new_lcov_hit_line_count"] = len(final_lines - replay_lines)
                fuzzed["empty_corpus_replay_lcov_hit_line_count"] = len(empty_replay_lines)
                fuzzed["native_lcov_hit_line_count"] = native["lcov_hit_line_count"]
                campaigns.extend([replay, empty_replay, native, fuzzed])
                write_json(OUTPUT / "Echidna逐次原始结果.json", {
                    "plan_sha256": sha256_file(plan_path),
                    "campaigns": campaigns})
                print(sample_id, seed, "replay", replay["lcov_hit_line_count"],
                      "replay-marginal", len(replay_lines - empty_replay_lines),
                      "fuzz-new", fuzzed["new_lcov_hit_line_count"],
                      "final", fuzzed["lcov_hit_line_count"], flush=True)
    summary = {
        "plan_sha256": sha256_file(plan_path),
        "campaign_count": len(campaigns),
        "campaigns": campaigns,
        "group_summary": []}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in campaigns:
        grouped.setdefault((row["sample_id"], row["treatment"]), []).append(row)
    for (sample_id, treatment), rows in sorted(grouped.items()):
        summary["group_summary"].append({
            "sample_id": sample_id,
            "treatment": treatment,
            "runs": len(rows),
            "completed_runs": sum(row["status"] == "completed" and row["exit_code"] == 0
                                  for row in rows),
            "property_failure_runs": sum(bool(row["property_failures"]) for row in rows),
            "mean_unique_instructions": statistics.mean(
                row["unique_instructions"] or 0 for row in rows),
            "mean_lcov_hit_line_count": statistics.mean(
                row["lcov_hit_line_count"] for row in rows),
            "mean_process_elapsed_seconds": statistics.mean(
                row["process_elapsed_seconds"] for row in rows),
            "mean_full_campaign_wall_seconds": statistics.mean(
                row["full_campaign_wall_seconds"] for row in rows),
            "mean_new_lcov_hit_line_count": (
                statistics.mean(row["new_lcov_hit_line_count"] for row in rows)
                if treatment == "seeded_fuzz" else None),
            "mean_seed_only_marginal_lcov_hit_line_count": (
                statistics.mean(row["seed_only_marginal_lcov_hit_line_count"]
                                for row in rows)
                if treatment == "seeded_fuzz" else None),
            "replay_runs": sum(bool(row["external_seed_replayed"]) for row in rows),
            "mutation_runs": sum(bool(row["mutation_evidence"]) for row in rows)})
    write_json(OUTPUT / "Phase26原始汇总.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--freeze-only", action="store_true")
    modes.add_argument("--run-frozen", action="store_true")
    args = parser.parse_args()
    if args.freeze_only:
        print(json.dumps(freeze(), ensure_ascii=False, indent=2))
    else:
        result = run_frozen()
        print(json.dumps(result["group_summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
