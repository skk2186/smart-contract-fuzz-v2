#!/usr/bin/env python3
"""M2-Plus：零修改接入 15 个官方 SmartBugs Curated 与 Trail of Bits Echidna 基准合约，完成编译、Slither、Anvil 与 Native Echidna 摸底。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path("/home/skk/smart-contract-fuzz-v2")
SB_DS = ROOT / ".tools/smartbugs-curated/dataset"
TOB_EX = ROOT / ".tools/building-secure-contracts/program-analysis/echidna/exercises"
OLYMPIA_PY = str(ROOT / ".tools/olympia-venv/bin/python")
PY311 = str(ROOT / ".tools/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python")
PROFILE_DIR = ROOT / "func/测试过程/SCFuzzBench公开项目接入/项目配置"
RESULT_DIR = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/M2Plus大规模基准集"

SOLC_0424 = "/home/skk/.solc-select/artifacts/solc-0.4.24/solc-0.4.24"
SOLC_0425 = "/home/skk/.solc-select/artifacts/solc-0.4.25/solc-0.4.25"
SOLC_0820 = "/home/skk/.solc-select/artifacts/solc-0.8.20/solc-0.8.20"

SENDERS = [
    "0x0000000000000000000000000000000000010000",
    "0x0000000000000000000000000000000000020000",
    "0x0000000000000000000000000000000000030000",
    "0x0000000000000000000000000000000000040000",
    "0x0000000000000000000000000000000000050000",
]

# Each entry copies untouched upstream .sol file(s) and adds a thin Echidna property Harness
# (for ToB exercises, the official solution.sol already has native echidna_* properties!).
EXTERNAL_SPECS: list[dict[str, Any]] = [
    {
        "name": "SB_Wallet03WrongConstructor",
        "source_type": "smartbugs-curated",
        "upstream_files": [("SB", "access_control/wallet_03_wrong_constructor.sol", "wallet_03_wrong_constructor.sol")],
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "harness_file": "Harness.sol",
        "contract": "SBWallet03Harness",
        "property_name": "echidna_only_deployer_keeps_funds",
        "dep_type": "wrong_constructor_takeover_and_drain",
        "harness_code": """pragma solidity ^0.4.24;
import "./wallet_03_wrong_constructor.sol";

contract SBWallet03Harness is Wallet {
    address public initialDeployer;
    uint256 public totalDeposited;
    bool public unauthorizedDrain;

    constructor() public {
        initialDeployer = msg.sender;
        creator = msg.sender;
    }

    function depositFunds() public payable {
        require(msg.value > 0);
        totalDeposited += msg.value;
        deposit();
    }

    function migrateFunds(address to) public {
        uint256 beforeBal = address(this).balance;
        migrateTo(to);
        if (beforeBal > 0 && msg.sender != initialDeployer) {
            unauthorizedDrain = true;
        }
    }

    function echidna_only_deployer_keeps_funds() public view returns (bool) {
        return !unauthorizedDrain;
    }
}
""",
    },
    {
        "name": "SB_Wallet04ConfusedSign",
        "source_type": "smartbugs-curated",
        "upstream_files": [("SB", "access_control/wallet_04_confused_sign.sol", "wallet_04_confused_sign.sol")],
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "harness_file": "Harness.sol",
        "contract": "SBWallet04Harness",
        "property_name": "echidna_withdraw_bounded_by_deposit",
        "dep_type": "cross_account_confused_sign_overwithdraw",
        "harness_code": """pragma solidity ^0.4.24;
import "./wallet_04_confused_sign.sol";

contract SBWallet04Harness is Wallet {
    mapping(address => uint256) public trackedDeposit;
    mapping(address => uint256) public trackedWithdraw;
    bool public overWithdrawn;

    function depositTracked() public payable {
        require(msg.value > 0);
        trackedDeposit[msg.sender] += msg.value;
        deposit();
    }

    function withdrawTracked(uint256 amount) public {
        require(amount > 0);
        withdraw(amount);
        trackedWithdraw[msg.sender] += amount;
        if (trackedWithdraw[msg.sender] > trackedDeposit[msg.sender]) {
            overWithdrawn = true;
        }
    }

    function echidna_withdraw_bounded_by_deposit() public view returns (bool) {
        return !overWithdrawn;
    }
}
""",
    },
    {
        "name": "SB_ArbitraryLocationWrite",
        "source_type": "smartbugs-curated",
        "upstream_files": [("SB", "access_control/arbitrary_location_write_simple.sol", "arbitrary_location_write_simple.sol")],
        "solc_version": "0.4.25",
        "solc_bin": SOLC_0425,
        "harness_file": "Harness.sol",
        "contract": "SBArbitraryWriteHarness",
        "property_name": "echidna_owner_slot_intact",
        "dep_type": "array_underflow_storage_slot_overwrite",
        "harness_code": """pragma solidity ^0.4.25;
import "./arbitrary_location_write_simple.sol";

contract SBArbitraryWriteHarness is Wallet {
    address public expectedOwner;

    constructor() public {
        expectedOwner = msg.sender;
    }

    function currentSlot1Owner() public view returns (address o) {
        assembly { o := sload(1) }
    }

    function bonusCodesLength() public view returns (uint256 l) {
        assembly { l := sload(0) }
    }

    function echidna_owner_slot_intact() public view returns (bool) {
        return currentSlot1Owner() == expectedOwner;
    }
}
""",
    },
    {
        "name": "SB_MappingWrite",
        "source_type": "smartbugs-curated",
        "upstream_files": [("SB", "access_control/mapping_write.sol", "mapping_write.sol")],
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "harness_file": "Harness.sol",
        "contract": "SBMappingWriteHarness",
        "property_name": "echidna_owner_unchanged",
        "dep_type": "dynamic_array_keccak_slot_overwrite",
        "harness_code": """pragma solidity ^0.4.24;
import "./mapping_write.sol";

contract SBMappingWriteHarness is Map {
    address public initialOwner;

    constructor() public {
        owner = msg.sender;
        initialOwner = msg.sender;
    }

    function echidna_owner_unchanged() public view returns (bool) {
        return owner == initialOwner;
    }
}
""",
    },
    {
        "name": "SB_MultiOwnable",
        "source_type": "smartbugs-curated",
        "upstream_files": [("SB", "access_control/multiowned_vulnerable.sol", "multiowned_vulnerable.sol")],
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "harness_file": "Harness.sol",
        "contract": "SBMultiOwnableHarness",
        "property_name": "echidna_non_root_cannot_drain",
        "dep_type": "unprotected_new_owner_and_drain",
        "harness_code": """pragma solidity ^0.4.24;
import "./multiowned_vulnerable.sol";

contract SBMultiOwnableHarness is TestContract {
    bool public nonRootDrained;

    function fundVault() public payable {
        require(msg.value > 0);
    }

    function guardedWithdrawAll() public {
        uint256 beforeBal = address(this).balance;
        withdrawAll();
        if (beforeBal > 0 && msg.sender != root) {
            nonRootDrained = true;
        }
    }

    function echidna_non_root_cannot_drain() public view returns (bool) {
        return !nonRootDrained;
    }
}
""",
    },
    {
        "name": "SB_IncorrectConstructor1",
        "source_type": "smartbugs-curated",
        "upstream_files": [("SB", "access_control/incorrect_constructor_name1.sol", "incorrect_constructor_name1.sol")],
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "harness_file": "Harness.sol",
        "contract": "SBIncorrectCtor1Harness",
        "property_name": "echidna_funds_not_stolen",
        "dep_type": "incorrect_ctor_takeover_and_withdraw",
        "harness_code": """pragma solidity ^0.4.24;
import "./incorrect_constructor_name1.sol";

contract SBIncorrectCtor1Harness is Missing {
    address public deployerAddr;
    bool public stolen;

    constructor() public {
        deployerAddr = msg.sender;
    }

    function fund() public payable {
        require(msg.value > 0);
    }

    function withdrawFunds() public {
        uint256 beforeBal = address(this).balance;
        withdraw();
        if (beforeBal > 0 && msg.sender != deployerAddr) {
            stolen = true;
        }
    }

    function echidna_funds_not_stolen() public view returns (bool) {
        return !stolen;
    }
}
""",
    },
    {
        "name": "SB_IncorrectConstructor2",
        "source_type": "smartbugs-curated",
        "upstream_files": [("SB", "access_control/incorrect_constructor_name2.sol", "incorrect_constructor_name2.sol")],
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "harness_file": "Harness.sol",
        "contract": "SBIncorrectCtor2Harness",
        "property_name": "echidna_funds_not_stolen",
        "dep_type": "incorrect_ctor_takeover_and_withdraw",
        "harness_code": """pragma solidity ^0.4.24;
import "./incorrect_constructor_name2.sol";

contract SBIncorrectCtor2Harness is Missing {
    address public deployerAddr;
    bool public stolen;

    constructor() public {
        deployerAddr = msg.sender;
    }

    function fund() public payable {
        require(msg.value > 0);
    }

    function withdrawFunds() public {
        uint256 beforeBal = address(this).balance;
        withdraw();
        if (beforeBal > 0 && msg.sender != deployerAddr) {
            stolen = true;
        }
    }

    function echidna_funds_not_stolen() public view returns (bool) {
        return !stolen;
    }
}
""",
    },
    {
        "name": "SB_IncorrectConstructor3",
        "source_type": "smartbugs-curated",
        "upstream_files": [("SB", "access_control/incorrect_constructor_name3.sol", "incorrect_constructor_name3.sol")],
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "harness_file": "Harness.sol",
        "contract": "SBIncorrectCtor3Harness",
        "property_name": "echidna_funds_not_stolen",
        "dep_type": "incorrect_ctor_takeover_and_withdraw",
        "harness_code": """pragma solidity ^0.4.24;
import "./incorrect_constructor_name3.sol";

contract SBIncorrectCtor3Harness is Missing {
    address public deployerAddr;
    bool public stolen;

    constructor() public {
        deployerAddr = msg.sender;
    }

    function fund() public payable {
        require(msg.value > 0);
    }

    function withdrawFunds() public {
        uint256 beforeBal = address(this).balance;
        withdraw();
        if (beforeBal > 0 && msg.sender != deployerAddr) {
            stolen = true;
        }
    }

    function echidna_funds_not_stolen() public view returns (bool) {
        return !stolen;
    }
}
""",
    },
    {
        "name": "SB_IntegerOverflowMultiTx",
        "source_type": "smartbugs-curated",
        "upstream_files": [("SB", "arithmetic/integer_overflow_multitx_multifunc_feasible.sol", "integer_overflow_multitx_multifunc_feasible.sol")],
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "harness_file": "Harness.sol",
        "contract": "SBMultiTxOverflowHarness",
        "property_name": "echidna_count_no_underflow",
        "dep_type": "two_function_state_init_then_underflow",
        "harness_code": """pragma solidity ^0.4.24;
import "./integer_overflow_multitx_multifunc_feasible.sol";

contract SBMultiTxOverflowHarness is IntegerOverflowMultiTxMultiFuncFeasible {
    function echidna_count_no_underflow() public view returns (bool) {
        return count <= 1;
    }
}
""",
    },
    {
        "name": "SB_IntegerOverflowMultiTxOneFunc",
        "source_type": "smartbugs-curated",
        "upstream_files": [("SB", "arithmetic/integer_overflow_multitx_onefunc_feasible.sol", "integer_overflow_multitx_onefunc_feasible.sol")],
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "harness_file": "Harness.sol",
        "contract": "SBOneFuncOverflowHarness",
        "property_name": "echidna_count_no_underflow",
        "dep_type": "same_function_two_step_underflow",
        "harness_code": """pragma solidity ^0.4.24;
import "./integer_overflow_multitx_onefunc_feasible.sol";

contract SBOneFuncOverflowHarness is IntegerOverflowMultiTxOneFuncFeasible {
    function echidna_count_no_underflow() public view returns (bool) {
        return count <= 1;
    }
}
""",
    },
    {
        "name": "SB_TokenUnderflow",
        "source_type": "smartbugs-curated",
        "upstream_files": [("SB", "arithmetic/token.sol", "token.sol")],
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "harness_file": "Harness.sol",
        "contract": "SBTokenUnderflowHarness",
        "property_name": "echidna_balances_bounded_by_supply",
        "dep_type": "erc20_transfer_subtraction_underflow",
        "harness_code": """pragma solidity ^0.4.24;
import "./token.sol";

contract SBTokenUnderflowHarness is Token {
    address public constant USER1 = 0x0000000000000000000000000000000000010000;
    address public constant USER2 = 0x0000000000000000000000000000000000020000;

    constructor() Token(1000) public {
        balances[USER1] = 20;
    }

    function echidna_balances_bounded_by_supply() public view returns (bool) {
        return balances[USER1] <= totalSupply && balances[USER2] <= totalSupply;
    }
}
""",
    },
    {
        "name": "SB_NameRegistrar",
        "source_type": "smartbugs-curated",
        "upstream_files": [("SB", "other/name_registrar.sol", "name_registrar.sol")],
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "harness_file": "Harness.sol",
        "contract": "SBNameRegistrarHarness",
        "property_name": "echidna_registrar_stays_locked",
        "dep_type": "uninitialized_storage_pointer_slot0_overwrite",
        "harness_code": """pragma solidity ^0.4.24;
import "./name_registrar.sol";

contract SBNameRegistrarHarness is NameRegistrar {
    function echidna_registrar_stays_locked() public view returns (bool) {
        return !unlocked;
    }
}
""",
    },
    {
        "name": "ToB_Exercise1",
        "source_type": "trailofbits-building-secure-contracts",
        "upstream_files": [
            ("TOB", "exercise1/token.sol", "token.sol"),
            ("TOB", "exercise1/solution.sol", "solution.sol"),
        ],
        "solc_version": "0.8.20",
        "solc_bin": SOLC_0820,
        "harness_file": "solution.sol",
        "contract": "TestToken",
        "property_name": "echidna_test_balance",
        "dep_type": "tob_unchecked_transfer_underflow",
        "harness_code": None,  # Official upstream solution.sol already has echidna_test_balance()!
    },
    {
        "name": "ToB_Exercise2",
        "source_type": "trailofbits-building-secure-contracts",
        "upstream_files": [
            ("TOB", "exercise2/token.sol", "token.sol"),
            ("TOB", "exercise2/solution.sol", "solution.sol"),
        ],
        "solc_version": "0.8.20",
        "solc_bin": SOLC_0820,
        "harness_file": "solution.sol",
        "contract": "TestToken",
        "property_name": "echidna_no_transfer",
        "dep_type": "tob_two_step_owner_takeover_and_unpause",
        "harness_code": None,  # Official upstream solution.sol already has echidna_no_transfer()!
    },
    {
        "name": "ToB_Exercise3",
        "source_type": "trailofbits-building-secure-contracts",
        "upstream_files": [
            ("TOB", "exercise3/token.sol", "token.sol"),
            ("TOB", "exercise3/mintable.sol", "mintable.sol"),
            ("TOB", "exercise3/solution.sol", "solution.sol"),
        ],
        "solc_version": "0.8.20",
        "solc_bin": SOLC_0820,
        "harness_file": "solution.sol",
        "contract": "TestToken",
        "property_name": "echidna_test_balance",
        "dep_type": "tob_signed_cast_mint_cap_bypass",
        "harness_code": None,  # Official upstream solution.sol already has echidna_test_balance()!
    },
]


def step1_materialize_and_analyze() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "func/功能") + ":" + env.get("PYTHONPATH", "")
    (RESULT_DIR / "分析产物").mkdir(parents=True, exist_ok=True)
    prop_ids: dict[str, str] = {}

    for spec in EXTERNAL_SPECS:
        name = spec["name"]
        sol_dir = ROOT / "sol/单合约测试" / name
        sol_dir.mkdir(parents=True, exist_ok=True)
        for src_kind, src_rel, dst_name in spec["upstream_files"]:
            src = (SB_DS if src_kind == "SB" else TOB_EX) / src_rel
            shutil.copy2(src, sol_dir / dst_name)
        if spec["harness_code"] is not None:
            (sol_dir / spec["harness_file"]).write_text(spec["harness_code"], encoding="utf-8")

        target_sol = sol_dir / spec["harness_file"]
        cfg = {
            "schema_version": 1,
            "project_name": name,
            "v2_enabled": True,
            "source": {
                "repository": (
                    "https://github.com/smartbugs/smartbugs-curated"
                    if spec["source_type"] == "smartbugs-curated"
                    else "https://github.com/crytic/building-secure-contracts"
                ),
                "commit": (
                    "230e649123477eff332742a59a1c7cc6dc286cab"
                    if spec["source_type"] == "smartbugs-curated"
                    else "HEAD"
                ),
                "root": str(sol_dir.relative_to(ROOT)),
            },
            "paths": {
                "analysis_report": f"func/测试过程/SCFuzzBench公开项目接入/结果/M2Plus大规模基准集/分析产物/{name}-slither.json",
                "compiled_artifact": f"func/测试过程/SCFuzzBench公开项目接入/结果/M2Plus大规模基准集/分析产物/{name}-compile.json",
            },
            "compiler": {
                "build_system": "solc",
                "target": str(target_sol),
                "version": spec["solc_version"],
                "solc": spec["solc_bin"],
                "remappings": [],
                "extra_args": [],
                "compile_options": {"compile_force_framework": "solc", "cwd": "/tmp"},
            },
            "harness": {"source": spec["harness_file"], "contract": spec["contract"]},
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
                "target_property": f"{spec['contract']}.{spec['property_name']}()",
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
            "medusa": {"test_prefixes": ["echidna_"], "test_mode": "property", "status": "ready"},
        }
        cfg_path = PROFILE_DIR / f"{name}.json"
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        print(f"[PREP] {name} ...", flush=True)
        subprocess.run(
            [OLYMPIA_PY, str(ROOT / "func/功能/编译测试环境.py"), name, "--solc", spec["solc_bin"]],
            check=True, env=env, cwd=str(ROOT),
        )
        rep_path = ROOT / cfg["paths"]["analysis_report"]
        subprocess.run(
            [
                OLYMPIA_PY, str(ROOT / "func/功能/属性分析适配器.py"),
                str(target_sol), "--contract", spec["contract"],
                "--solc", spec["solc_bin"], "--output", str(rep_path),
            ],
            check=True, env=env, cwd=str(ROOT),
        )
        rep = json.loads(rep_path.read_text(encoding="utf-8"))
        prop = next(p for p in rep["properties"] if spec["property_name"] in p["property"])
        cfg["property"]["target_property_id"] = prop["property_id"]
        cfg["property"]["target_property"] = prop["property"]
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        prop_ids[name] = prop["property_id"]
        print(f"  -> OK id={prop['property_id']}", flush=True)
    return prop_ids


def step2_probe_15(prop_ids: dict[str, str]) -> None:
    sys.path[:0] = [
        str(ROOT / ".tools/phase43-runtime-py311"),
        str(ROOT / "deepseek"),
        str(ROOT / "func/功能"),
    ]
    from 属性种子上下文 import load_project_context
    from 种子验证 import AnvilSession, inspect_initial_state, run_echidna

    probe_root = RESULT_DIR / "Native摸底_15外部"
    if probe_root.exists():
        shutil.rmtree(probe_root)
    probe_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for idx, spec in enumerate(EXTERNAL_SPECS, start=1):
        name = spec["name"]
        pid = prop_ids[name]
        pname = spec["property_name"]
        row: dict[str, Any] = {
            "index": idx,
            "group": "A1_PublicClassic",
            "source_type": spec["source_type"],
            "project": name,
            "property_id": pid,
            "property_name": pname,
            "dependency_type": spec["dep_type"],
        }
        try:
            ctx = load_project_context(name, [pid])
            prop = ctx["properties"][0]
            actions = [a["abi_signature"] for a in prop.get("candidate_actions", []) if a.get("seed_compatible")]
            row["candidate_action_count"] = len(actions)
            row["candidate_actions"] = actions
            with AnvilSession(project=name) as sess:
                init = inspect_initial_state(name, prop, session=sess)
            pval = (init.get("initial_properties") or {}).get(pname + "()")
            row["anvil_deploy_status"] = init.get("status")
            row["anvil_initial_property"] = pval

            cdir = probe_root / name / "native_seed_20261128"
            cdir.mkdir(parents=True, exist_ok=True)
            res = run_echidna(
                name, cdir, property_name=pname,
                test_limit=20000, timeout=30, seed=20261128,
                test_mode="property", property_prefix=pname,
                seq_len=10, stop_on_fail=True, disable_slither=True,
            )
            row["native_status"] = res.get("status")
            row["native_falsified"] = bool(res.get("property_failures"))
            row["native_elapsed_seconds"] = res.get("elapsed_seconds")
            row["native_unique_instructions"] = res.get("unique_instructions")
            row["native_fuzzing_txs"] = res.get("fuzzing_transactions")
            row["admission_status"] = (
                "admitted"
                if (init.get("status") == "observed" and pval is True and len(actions) > 0 and res.get("unique_instructions"))
                else "needs_review"
            )
            print(
                f"[{idx:02d}/15] {name}: actions={len(actions)} init={pval} "
                f"native_ce={row['native_falsified']} t={row['native_elapsed_seconds']}s "
                f"instr={row['native_unique_instructions']} txs={row['native_fuzzing_txs']} -> {row['admission_status']}",
                flush=True,
            )
        except Exception as exc:
            row["admission_status"] = "failed"
            row["error"] = f"{type(exc).__name__}: {str(exc)[:400]}"
            print(f"[{idx:02d}/15] {name}: ERR {row['error']}", flush=True)
        rows.append(row)

    out_path = RESULT_DIR / "external_15_probe.json"
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    admitted = sum(r["admission_status"] == "admitted" for r in rows)
    nat_ce = sum(bool(r.get("native_falsified")) for r in rows)
    print(f"\n=== 15 EXTERNAL DONE: admitted={admitted}/15, native_falsified={nat_ce}/15 ===", flush=True)


def main() -> None:
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    ids_path = RESULT_DIR / "external_15_prop_ids.json"
    if phase == "prep":
        ids = step1_materialize_and_analyze()
        ids_path.write_text(json.dumps(ids, indent=2), encoding="utf-8")
    elif phase == "probe":
        ids = json.loads(ids_path.read_text(encoding="utf-8"))
        step2_probe_15(ids)
    else:
        ids = step1_materialize_and_analyze()
        ids_path.write_text(json.dumps(ids, indent=2), encoding="utf-8")
        subprocess.run([PY311, str(Path(__file__).resolve()), "probe"], check=True)


if __name__ == "__main__":
    main()
