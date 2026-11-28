#!/usr/bin/env python3
"""M2 正式论文基准集（20 任务）自动化配置生成、编译、Slither 属性分析、Anvil 核验与 Native Echidna 摸底。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OLYMPIA_PY = str(ROOT / ".tools/olympia-venv/bin/python")
PY311 = str(ROOT / ".tools/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python")
PROFILE_DIR = ROOT / "func/测试过程/SCFuzzBench公开项目接入/项目配置"
RESULT_DIR = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/M2正式基准集"

SOLC_0820 = "/home/skk/.solc-select/artifacts/solc-0.8.20/solc-0.8.20"
SOLC_0425 = "/home/skk/.solc-select/artifacts/solc-0.4.25/solc-0.4.25"

SENDERS = [
    "0x0000000000000000000000000000000000010000",
    "0x0000000000000000000000000000000000020000",
    "0x0000000000000000000000000000000000030000",
    "0x0000000000000000000000000000000000040000",
    "0x0000000000000000000000000000000000050000",
]

NEW_BENCHMARKS = [
    # Benchmark A1: Public Classic Multi-Tx Vulnerabilities (5 new + 3 from M1 = 8)
    {
        "group": "A1_PublicClassic",
        "name": "EthernautNaughtCoin",
        "contract": "EthernautNaughtCoinHarness",
        "sol_rel": "sol/单合约测试/EthernautNaughtCoin/EthernautNaughtCoinHarness.sol",
        "solc_version": "0.8.20",
        "solc_bin": SOLC_0820,
        "repo": "https://github.com/OpenZeppelin/ethernaut",
        "commit": "level-15-naught-coin-self-contained",
        "dep_type": "timelock_cross_account_allowance_bypass",
        "property_name": "echidna_locked_balance_not_drained",
    },
    {
        "group": "A1_PublicClassic",
        "name": "EthernautDexTwo",
        "contract": "EthernautDexTwoHarness",
        "sol_rel": "sol/单合约测试/EthernautDexTwo/EthernautDexTwoHarness.sol",
        "solc_version": "0.8.20",
        "solc_bin": SOLC_0820,
        "repo": "https://github.com/OpenZeppelin/ethernaut",
        "commit": "level-23-dex-two-self-contained",
        "dep_type": "cross_contract_erc20_missing_allowlist_dual_drain",
        "property_name": "echidna_both_reserves_not_drained",
    },
    {
        "group": "A1_PublicClassic",
        "name": "CTETokenSale",
        "contract": "CTETokenSaleHarness",
        "sol_rel": "sol/单合约测试/CTETokenSale/CTETokenSaleHarness.sol",
        "solc_version": "0.4.25",
        "solc_bin": SOLC_0425,
        "repo": "https://capturetheether.com/challenges/math/token-sale/",
        "commit": "capture-the-ether-token-sale",
        "dep_type": "multi_tx_mul_overflow_eth_drain",
        "property_name": "echidna_pool_not_drained_below_seed",
    },
    {
        "group": "A1_PublicClassic",
        "name": "SmartBugsTimeLock",
        "contract": "SmartBugsTimeLockHarness",
        "sol_rel": "sol/单合约测试/SmartBugsTimeLock/SmartBugsTimeLockHarness.sol",
        "solc_version": "0.4.25",
        "solc_bin": SOLC_0425,
        "repo": "https://github.com/smartbugs/smartbugs-curated",
        "commit": "dataset/arithmetic/timelock.sol",
        "dep_type": "stateful_timestamp_overflow_bypass",
        "property_name": "echidna_no_early_withdrawal",
    },
    {
        "group": "A1_PublicClassic",
        "name": "SmartBugsBECToken",
        "contract": "SmartBugsBECTokenHarness",
        "sol_rel": "sol/单合约测试/SmartBugsBECToken/SmartBugsBECTokenHarness.sol",
        "solc_version": "0.4.25",
        "solc_bin": SOLC_0425,
        "repo": "https://github.com/smartbugs/smartbugs-curated",
        "commit": "CVE-2018-10299-BECToken",
        "dep_type": "dynamic_address_array_mul_overflow",
        "property_name": "echidna_supply_conserved",
    },
    # Benchmark A2: DeFi Deep State-Machine & Dynamic Hash-ID Patterns (6)
    {
        "group": "A2_DeFiStateful",
        "name": "DeFiERC4626Inflation",
        "contract": "DeFiERC4626InflationHarness",
        "sol_rel": "sol/单合约测试/DeFiERC4626Inflation/DeFiERC4626InflationHarness.sol",
        "solc_version": "0.8.20",
        "solc_bin": SOLC_0820,
        "repo": "representative-defi-pattern/erc4626-inflation",
        "commit": "v1",
        "dep_type": "cross_account_allowance_vault_share_inflation",
        "property_name": "echidna_no_zero_share_deposit_loss",
    },
    {
        "group": "A2_DeFiStateful",
        "name": "DeFiGovDoubleVote",
        "contract": "DeFiGovDoubleVoteHarness",
        "sol_rel": "sol/单合约测试/DeFiGovDoubleVote/DeFiGovDoubleVoteHarness.sol",
        "solc_version": "0.8.20",
        "solc_bin": SOLC_0820,
        "repo": "representative-defi-pattern/governance-double-vote",
        "commit": "v1",
        "dep_type": "dynamic_bytes32_event_id_cross_account_timelock",
        "property_name": "echidna_quorum_cannot_be_exceeded",
    },
    {
        "group": "A2_DeFiStateful",
        "name": "DeFiOracleLending",
        "contract": "DeFiOracleLendingHarness",
        "sol_rel": "sol/单合约测试/DeFiOracleLending/DeFiOracleLendingHarness.sol",
        "solc_version": "0.8.20",
        "solc_bin": SOLC_0820,
        "repo": "representative-defi-pattern/amm-spot-oracle-lending",
        "commit": "v1",
        "dep_type": "amm_spot_price_manipulation_bad_debt",
        "property_name": "echidna_lending_pool_no_bad_debt",
    },
    {
        "group": "A2_DeFiStateful",
        "name": "DeFiEscrowHashId",
        "contract": "DeFiEscrowHashIdHarness",
        "sol_rel": "sol/单合约测试/DeFiEscrowHashId/DeFiEscrowHashIdHarness.sol",
        "solc_version": "0.8.20",
        "solc_bin": SOLC_0820,
        "repo": "representative-defi-pattern/escrow-hash-id-double-claim",
        "commit": "v1",
        "dep_type": "dynamic_bytes32_event_id_multi_role_state_machine",
        "property_name": "echidna_escrow_solvency",
    },
    {
        "group": "A2_DeFiStateful",
        "name": "DeFiAuctionTimeId",
        "contract": "DeFiAuctionTimeIdHarness",
        "sol_rel": "sol/单合约测试/DeFiAuctionTimeId/DeFiAuctionTimeIdHarness.sol",
        "solc_version": "0.8.20",
        "solc_bin": SOLC_0820,
        "repo": "representative-defi-pattern/auction-hash-id-timelock",
        "commit": "v1",
        "dep_type": "dynamic_bytes32_event_id_multi_bidder_timelock",
        "property_name": "echidna_auction_accounting_conserved",
    },
    {
        "group": "A2_DeFiStateful",
        "name": "DeFiMultiSigBypass",
        "contract": "DeFiMultiSigBypassHarness",
        "sol_rel": "sol/单合约测试/DeFiMultiSigBypass/DeFiMultiSigBypassHarness.sol",
        "solc_version": "0.8.20",
        "solc_bin": SOLC_0820,
        "repo": "representative-defi-pattern/multisig-revoke-desync",
        "commit": "v1",
        "dep_type": "dynamic_bytes32_event_id_5step_state_machine",
        "property_name": "echidna_threshold_requires_distinct_signers",
    },
]

ALL_M2_TASKS = [
    # A1 (8)
    ("A1_PublicClassic", "Wallet02Refund", "8e75f62866f6d582a033", "echidna_wallet_accounting_respected", "multi_account_shared_eth_pool"),
    ("A1_PublicClassic", "EthernautDex", "36dfdfaa21bb1b408da9", "echidna_dex_reserves_non_empty", "erc20_allowance_7step_amm_drain"),
    ("A1_PublicClassic", "TokenWhale", "85ecbb71ea3e7168edab", "echidna_no_token_inflation", "cross_account_allowance_underflow"),
    *[
        (item["group"], item["name"], "", item["property_name"], item["dep_type"])
        for item in NEW_BENCHMARKS
    ],
    # B: Real-World Multi-Contract Protocols (6)
    ("B_RealMultiContract", "Request", "bc39edeb78eed12c3bea", "echidna_captured_never_exceeds_authorized", "real_escrow_payment_lifecycle"),
    ("B_RealMultiContract", "BeeStorage", "2c68514fc72b1303d6e8", "echidna_stamp_internal_pot_not_above_contract_balance", "real_dynamic_batchid_pot_accounting"),
    ("B_RealMultiContract", "Immutable", "3e35d725a8e008691349", "echidna_approval_consistency", "real_erc721_mint_approve_tokenid"),
    ("B_RealMultiContract", "OpenNFTs", "50cc31144be4bad9bc9d", "echidna_balance", "real_nft_mint_transfer_target"),
    ("B_RealMultiContract", "Hokusai", "ad28f4492fa527ee713b", "echidna_investor_cap", "real_role_controlled_token_cap"),
    ("B_RealMultiContract", "Kink", "f79b3b000df5bc77ba4a", "echidna_invariant_matches_supply", "real_defi_amm_invariant"),
]


def _write_profile(item: dict[str, Any]) -> Path:
    sol_path = ROOT / item["sol_rel"]
    cfg = {
        "schema_version": 1,
        "project_name": item["name"],
        "v2_enabled": True,
        "source": {
            "repository": item["repo"],
            "commit": item["commit"],
            "root": str(sol_path.parent.relative_to(ROOT)),
        },
        "paths": {
            "analysis_report": f"func/测试过程/SCFuzzBench公开项目接入/结果/M2正式基准集/分析产物/{item['name']}-slither.json",
            "compiled_artifact": f"func/测试过程/SCFuzzBench公开项目接入/结果/M2正式基准集/分析产物/{item['name']}-compile.json",
        },
        "compiler": {
            "build_system": "solc",
            "target": str(sol_path),
            "version": item["solc_version"],
            "solc": item["solc_bin"],
            "remappings": [],
            "extra_args": [],
            "compile_options": {
                "compile_force_framework": "solc",
                "cwd": "/tmp",
            },
        },
        "harness": {
            "source": sol_path.name,
            "contract": item["contract"],
        },
        "analysis": {"property_functions": []},
        "deployment": {
            "mode": "constructor",
            "constructor_args": [],
            "deployer": "0x0000000000000000000000000000000000030000",
            "contract_address": "0xA647ff3c36cFab592509E13860ab8c4F28781a66",
            "address_derivation": "CREATE(deployer, nonce=0)",
            "required_dependencies": [],
        },
        "execution": {
            "chain_id": 1,
            "deployment_timestamp": 1524785992,
            "deployment_block_number": 4370000,
            "base_fee_per_gas": 0,
            "gas_price": 0,
            "block_gas_limit": 100000000,
            "max_transaction_gas": 12500000,
            "initial_balance": 100000000000000000000,
            "hardfork": "shanghai",
        },
        "property": {
            "mode": "property",
            "engine_prefix": "echidna_",
            "sender": "0x0000000000000000000000000000000000010000",
            "target_property_id": "",
            "target_property": f"{item['contract']}.{item['property_name']}()",
        },
        "actions": {"senders": SENDERS},
        "echidna": {
            "prefix": "echidna_",
            "test_mode": "property",
            "workers": 1,
            "call_sequence_length": 10,
            "stop_on_fail": False,
            "disable_slither": True,
        },
        "medusa": {
            "test_prefixes": ["echidna_"],
            "test_mode": "property",
            "status": "ready",
        },
    }
    p = PROFILE_DIR / f"{item['name']}.json"
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def step1_prepare_new_benchmarks() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "func/功能") + ":" + env.get("PYTHONPATH", "")
    (RESULT_DIR / "分析产物").mkdir(parents=True, exist_ok=True)
    prop_ids: dict[str, str] = {}
    for item in NEW_BENCHMARKS:
        cfg_path = _write_profile(item)
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        print(f"[PREP] Compiling & analyzing {item['name']} ...", flush=True)
        subprocess.run(
            [OLYMPIA_PY, str(ROOT / "func/功能/编译测试环境.py"), item["name"], "--solc", item["solc_bin"]],
            check=True, env=env, cwd=str(ROOT),
        )
        rep_path = ROOT / cfg["paths"]["analysis_report"]
        subprocess.run(
            [
                OLYMPIA_PY, str(ROOT / "func/功能/属性分析适配器.py"),
                str(ROOT / item["sol_rel"]),
                "--contract", item["contract"],
                "--solc", item["solc_bin"],
                "--output", str(rep_path),
            ],
            check=True, env=env, cwd=str(ROOT),
        )
        rep = json.loads(rep_path.read_text(encoding="utf-8"))
        prop = next(p for p in rep["properties"] if item["property_name"] in p["property"])
        cfg["property"]["target_property_id"] = prop["property_id"]
        cfg["property"]["target_property"] = prop["property"]
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        prop_ids[item["name"]] = prop["property_id"]
        print(f"  -> OK id={prop['property_id']} class={prop['analysis_class']}", flush=True)
    return prop_ids


def step2_probe_all_20(new_prop_ids: dict[str, str]) -> None:
    sys.path[:0] = [
        str(ROOT / ".tools/phase43-runtime-py311"),
        str(ROOT / "deepseek"),
        str(ROOT / "func/功能"),
    ]
    from 属性种子上下文 import PROJECTS, load_project_context
    from 种子验证 import AnvilSession, inspect_initial_state, run_echidna

    probe_root = RESULT_DIR / "Native摸底"
    if probe_root.exists():
        shutil.rmtree(probe_root)
    probe_root.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    for idx, (group, proj, pid, prop_name, dep_type) in enumerate(ALL_M2_TASKS, start=1):
        prop_id = pid or new_prop_ids[proj]
        print(f"\n[{idx:02d}/20] {group} | {proj} ({prop_name})", flush=True)
        row: dict[str, Any] = {
            "task_index": idx,
            "group": group,
            "project": proj,
            "property_id": prop_id,
            "property_name": prop_name,
            "dependency_type": dep_type,
        }
        try:
            ctx = load_project_context(proj, [prop_id])
            prop = ctx["properties"][0]
            actions = [a["abi_signature"] for a in prop.get("candidate_actions", []) if a.get("seed_compatible")]
            guard_writers = [a["abi_signature"] for a in prop.get("candidate_actions", []) if a.get("action_source") == "prerequisite_guard_writer"]
            row["candidate_action_count"] = len(actions)
            row["candidate_actions"] = actions
            row["guard_writer_actions"] = guard_writers
            row["action_inventory_source"] = prop.get("action_inventory_source")

            with AnvilSession(project=proj) as sess:
                init = inspect_initial_state(proj, prop, session=sess)
            init_props = init.get("initial_properties") or {}
            prop_initial_val = init_props.get(prop_name + "()")
            row["anvil_deploy_status"] = init.get("status")
            row["anvil_initial_property"] = prop_initial_val
            row["anvil_view_count"] = init.get("view_count")

            corpus_dir = probe_root / proj / "native_seed_20261128"
            corpus_dir.mkdir(parents=True, exist_ok=True)
            res = run_echidna(
                proj,
                corpus_dir,
                property_name=prop_name,
                test_limit=20000,
                timeout=30,
                seed=20261128,
                test_mode="property",
                property_prefix=prop_name,
                seq_len=10,
                stop_on_fail=True,
                disable_slither=True,
            )
            row["native_status"] = res.get("status")
            row["native_exit_code"] = res.get("exit_code")
            row["native_falsified"] = bool(res.get("property_failures"))
            row["native_elapsed_seconds"] = res.get("elapsed_seconds")
            row["native_unique_instructions"] = res.get("unique_instructions")
            row["native_fuzzing_txs"] = res.get("fuzzing_transactions")
            row["admission_status"] = (
                "admitted"
                if (init.get("status") == "observed" and prop_initial_val is True and res.get("unique_instructions"))
                else "needs_review"
            )
            print(
                f"  actions={len(actions)} (guard_closure={len(guard_writers)}) | "
                f"anvil_init={prop_initial_val} | native_falsified={row['native_falsified']} "
                f"t={row['native_elapsed_seconds']}s instr={row['native_unique_instructions']} "
                f"txs={row['native_fuzzing_txs']} -> {row['admission_status']}",
                flush=True,
            )
        except Exception as exc:
            row["admission_status"] = "failed"
            row["error"] = f"{type(exc).__name__}: {str(exc)[:600]}"
            print(f"  ERROR: {row['error']}", flush=True)
        manifest_rows.append(row)

    manifest_path = RESULT_DIR / "dataset_manifest_m2.json"
    manifest_path.write_text(json.dumps(manifest_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    admitted = sum(r.get("admission_status") == "admitted" for r in manifest_rows)
    native_found = sum(bool(r.get("native_falsified")) for r in manifest_rows)
    print(f"\n=== M2 COMPLETE: admitted={admitted}/20, native_falsified={native_found}/20 ===", flush=True)
    print(f"Manifest saved: {manifest_path}", flush=True)


def main() -> None:
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"
    ids_cache = RESULT_DIR / "new_prop_ids.json"
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    if phase == "prep":
        ids = step1_prepare_new_benchmarks()
        ids_cache.write_text(json.dumps(ids, indent=2), encoding="utf-8")
    elif phase == "probe":
        ids = json.loads(ids_cache.read_text(encoding="utf-8"))
        step2_probe_all_20(ids)
    else:
        ids = step1_prepare_new_benchmarks()
        ids_cache.write_text(json.dumps(ids, indent=2), encoding="utf-8")
        subprocess.run([PY311, str(Path(__file__).resolve()), "probe"], check=True)


if __name__ == "__main__":
    main()
