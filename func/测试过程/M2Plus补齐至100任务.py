#!/usr/bin/env python3
"""M2-Plus 第二批：零修改接入 19 个官方 SmartBugs Curated 原文合约并汇总冻结 100 任务正式论文基准清单。"""

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
OLYMPIA_PY = str(ROOT / ".tools/olympia-venv/bin/python")
PY311 = str(ROOT / ".tools/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python")
PROFILE_DIR = ROOT / "func/测试过程/SCFuzzBench公开项目接入/项目配置"
RESULT_DIR = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/M2Plus大规模基准集"

SOLC_0424 = "/home/skk/.solc-select/artifacts/solc-0.4.24/solc-0.4.24"
SOLC_0425 = "/home/skk/.solc-select/artifacts/solc-0.4.25/solc-0.4.25"

SENDERS = [
    "0x0000000000000000000000000000000000010000",
    "0x0000000000000000000000000000000000020000",
    "0x0000000000000000000000000000000000030000",
    "0x0000000000000000000000000000000000040000",
    "0x0000000000000000000000000000000000050000",
]

BATCH2_SPECS: list[dict[str, Any]] = [
    {
        "name": "SB_PredictBlockHash",
        "src_rel": "bad_randomness/old_blockhash.sol",
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "contract": "SBPredictBlockHashHarness",
        "property_name": "echidna_house_keeps_prize",
        "dep_type": "block_delay_256_zero_blockhash_win",
        "harness_code": """pragma solidity ^0.4.24;
import "./old_blockhash.sol";

contract SBPredictBlockHashHarness {
    PredictTheBlockHashChallenge public target;
    bool public prizeWon;

    function initChallenge() public payable {
        require(address(target) == address(0) && msg.value == 1 ether);
        target = (new PredictTheBlockHashChallenge).value(1 ether)();
    }

    function lockGuess(bytes32 hash) public payable {
        require(address(target) != address(0) && msg.value == 1 ether);
        target.lockInGuess.value(1 ether)(hash);
    }

    function settleGuess() public {
        require(address(target) != address(0));
        uint256 beforeBal = address(target).balance;
        target.settle();
        if (beforeBal >= 2 ether && address(target).balance == 0) {
            prizeWon = true;
        }
    }

    function() public payable {}

    function echidna_house_keeps_prize() public view returns (bool) {
        return !prizeWon;
    }
}
""",
    },
    {
        "name": "SB_DosAddress",
        "src_rel": "denial_of_service/dos_address.sol",
        "solc_version": "0.4.25",
        "solc_bin": SOLC_0425,
        "contract": "SBDosAddressHarness",
        "property_name": "echidna_not_won_via_unbounded_loop",
        "dep_type": "multi_step_array_growth_threshold_1500",
        "harness_code": """pragma solidity ^0.4.25;
import "./dos_address.sol";

contract SBDosAddressHarness is DosGas {
    function echidna_not_won_via_unbounded_loop() public view returns (bool) {
        return !iWin();
    }
}
""",
    },
    {
        "name": "SB_DosNumber",
        "src_rel": "denial_of_service/dos_number.sol",
        "solc_version": "0.4.25",
        "solc_bin": SOLC_0425,
        "contract": "SBDosNumberHarness",
        "property_name": "echidna_array_below_dos_threshold",
        "dep_type": "multi_step_parameterized_array_growth",
        "harness_code": """pragma solidity ^0.4.25;
import "./dos_number.sol";

contract SBDosNumberHarness is DosNumber {
    function echidna_array_below_dos_threshold() public view returns (bool) {
        return getLengthArray() <= 1500;
    }
}
""",
    },
    {
        "name": "SB_DosSimple",
        "src_rel": "denial_of_service/dos_simple.sol",
        "solc_version": "0.4.25",
        "solc_bin": SOLC_0425,
        "contract": "SBDosSimpleHarness",
        "property_name": "echidna_list_never_reset_after_1500",
        "dep_type": "repeated_call_5step_array_overflow",
        "harness_code": """pragma solidity ^0.4.25;
import "./dos_simple.sol";

contract SBDosSimpleHarness is DosOneFunc {
    bool public resetTriggered;

    function fillStep() public {
        bool ok = ifillArray();
        if (!ok) {
            resetTriggered = true;
        }
    }

    function currentLength() public view returns (uint256) {
        return listAddresses.length;
    }

    function echidna_list_never_reset_after_1500() public view returns (bool) {
        return !resetTriggered;
    }
}
""",
    },
    {
        "name": "SB_Rubixi",
        "src_rel": "access_control/rubixi.sol",
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "contract": "SBRubixiHarness",
        "property_name": "echidna_fees_not_taken_by_non_deployer",
        "dep_type": "mainnet_wrong_ctor_fee_takeover",
        "harness_code": """pragma solidity ^0.4.24;
import "./rubixi.sol";

contract SBRubixiHarness is Rubixi {
    address public initialDeployer;
    bool public unauthorizedFeeCollect;

    constructor() public {
        initialDeployer = msg.sender;
        DynamicPyramid();
    }

    function contributeFee() public payable {
        require(msg.value > 0 && msg.value < 1 ether);
        // Trigger fallback fee accumulation through self-call or direct value
        require(address(this).call.value(msg.value)());
    }

    function guardedCollectAllFees() public {
        uint256 beforeBal = address(this).balance;
        collectAllFees();
        if (beforeBal > 0 && msg.sender != initialDeployer) {
            unauthorizedFeeCollect = true;
        }
    }

    function echidna_fees_not_taken_by_non_deployer() public view returns (bool) {
        return !unauthorizedFeeCollect;
    }
}
""",
    },
    {
        "name": "SB_TokenBankMainnet",
        "src_rel": "unchecked_low_level_calls/0x39cfd754c85023648bf003bea2dd498c5612abfa.sol",
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "contract": "SBTokenBankHarness",
        "property_name": "echidna_owner_preserved",
        "dep_type": "mainnet_unprotected_init_owner_takeover",
        "harness_code": """pragma solidity ^0.4.24;
import "./0x39cfd754c85023648bf003bea2dd498c5612abfa.sol";

contract SBTokenBankHarness is TokenBank {
    address public initialOwner;

    constructor() public {
        initTokenBank();
        initialOwner = msg.sender;
    }

    function currentOwner() public view returns (address) {
        return owner;
    }

    function echidna_owner_preserved() public view returns (bool) {
        return owner == initialOwner;
    }
}
""",
    },
    {
        "name": "SB_UnprotectedOwner",
        "src_rel": "access_control/unprotected0.sol",
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "contract": "SBUnprotectedHarness",
        "property_name": "echidna_only_initial_owner_privileged",
        "dep_type": "unprotected_change_owner_privilege_escalation",
        "harness_code": """pragma solidity ^0.4.24;
import "./unprotected0.sol";

contract SBUnprotectedHarness is Unprotected {
    address public initialOwner;
    bool public nonInitialTriggered;

    constructor() public {
        initialOwner = msg.sender;
    }

    function privilegedAction() public onlyowner {
        if (msg.sender != initialOwner) {
            nonInitialTriggered = true;
        }
    }

    function echidna_only_initial_owner_privileged() public view returns (bool) {
        return !nonInitialTriggered;
    }
}
""",
    },
    {
        "name": "SB_ERC20FrontRun",
        "src_rel": "front_running/ERC20.sol",
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "contract": "SBERC20FrontRunHarness",
        "property_name": "echidna_spender_respects_reduced_cap",
        "dep_type": "cross_account_erc20_approve_double_spend",
        "harness_code": """pragma solidity ^0.4.24;
import "./ERC20.sol";

contract SBERC20FrontRunHarness is ERC20 {
    address public constant OWNER = 0x0000000000000000000000000000000000010000;
    address public constant SPENDER = 0x0000000000000000000000000000000000020000;
    uint256 public highestSingleApproval;
    uint256 public totalSpentBySpender;
    bool public capExceededAfterReset;

    constructor() ERC20(1000) public {
        transfer(OWNER, 1000);
    }

    function ownerApprove(address spender, uint256 value) public {
        require(msg.sender == OWNER && spender == SPENDER && value > 0 && value <= 100);
        if (value > highestSingleApproval) {
            highestSingleApproval = value;
        }
        approve(spender, value);
    }

    function spenderPull(address to, uint256 value) public {
        require(msg.sender == SPENDER && value > 0);
        transferFrom(OWNER, to, value);
        totalSpentBySpender += value;
        if (highestSingleApproval > 0 && totalSpentBySpender > highestSingleApproval) {
            capExceededAfterReset = true;
        }
    }

    function echidna_spender_respects_reduced_cap() public view returns (bool) {
        return !capExceededAfterReset;
    }
}
""",
    },
    {
        "name": "SB_EthTxOrderDependence",
        "src_rel": "front_running/eth_tx_order_dependence_minimal.sol",
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "contract": "SBEthTxOrderHarness",
        "property_name": "echidna_reward_not_claimed_by_outsider",
        "dep_type": "multi_account_set_and_claim_reward",
        "harness_code": """pragma solidity ^0.4.24;
import "./eth_tx_order_dependence_minimal.sol";

contract SBEthTxOrderHarness is EthTxOrderDependenceMinimal {
    bool public outsiderClaimedNonZero;

    function ownerSetReward() public payable {
        require(msg.value >= 1 ether);
        setReward();
    }

    function userClaimReward(uint256 submission) public {
        uint256 r = reward;
        claimReward(submission);
        if (r >= 1 ether && msg.sender != owner) {
            outsiderClaimedNonZero = true;
        }
    }

    function echidna_reward_not_claimed_by_outsider() public view returns (bool) {
        return !outsiderClaimedNonZero;
    }
}
""",
    },
    {
        "name": "SB_OddsAndEvens",
        "src_rel": "front_running/odds_and_evens.sol",
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "contract": "SBOddsAndEvensHarness",
        "property_name": "echidna_second_player_cannot_always_win",
        "dep_type": "two_player_exact_1eth_frontrun_game",
        "harness_code": """pragma solidity ^0.4.24;
import "./odds_and_evens.sol";

contract SBOddsAndEvensHarness is OddsAndEvens {
    bool public roundCompleted;

    function playRound(uint256 number) public payable {
        uint8 beforeTot = tot;
        play(number);
        if (beforeTot == 1 && tot == 0) {
            roundCompleted = true;
        }
    }

    function echidna_second_player_cannot_always_win() public view returns (bool) {
        return !roundCompleted;
    }
}
""",
    },
    {
        "name": "SB_IntegerOverflow1",
        "src_rel": "arithmetic/integer_overflow_1.sol",
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "contract": "SBIntOverflow1Harness",
        "property_name": "echidna_seller_balance_monotonic",
        "dep_type": "stateful_add_overflow_wrap",
        "harness_code": """pragma solidity ^0.4.24;
import "./integer_overflow_1.sol";

contract SBIntOverflow1Harness is Overflow {
    uint256 public lastAdded;
    bool public wrapped;

    function addTracked(uint256 value) public {
        require(value > 0);
        uint256 prev = lastAdded;
        add(value);
        uint256 cur;
        assembly { cur := sload(0) }
        if (cur < prev || cur < value) {
            wrapped = true;
        }
        lastAdded = cur;
    }

    function echidna_seller_balance_monotonic() public view returns (bool) {
        return !wrapped;
    }
}
""",
    },
    {
        "name": "SB_IntegerOverflowAdd",
        "src_rel": "arithmetic/integer_overflow_add.sol",
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "contract": "SBIntOverflowAddHarness",
        "property_name": "echidna_count_never_zero",
        "dep_type": "arithmetic_add_overflow",
        "harness_code": """pragma solidity ^0.4.24;
import "./integer_overflow_add.sol";

contract SBIntOverflowAddHarness is IntegerOverflowAdd {
    function echidna_count_never_zero() public view returns (bool) {
        return count >= 1;
    }
}
""",
    },
    {
        "name": "SB_IntegerOverflowMul",
        "src_rel": "arithmetic/integer_overflow_mul.sol",
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "contract": "SBIntOverflowMulHarness",
        "property_name": "echidna_count_never_wraps_to_zero",
        "dep_type": "arithmetic_mul_overflow_exact_wrap",
        "harness_code": """pragma solidity ^0.4.24;
import "./integer_overflow_mul.sol";

contract SBIntOverflowMulHarness is IntegerOverflowMul {
    bool public overflowedToZero;

    function runNonZero(uint256 input) public {
        require(input > 0);
        uint256 beforeVal = count;
        run(input);
        if (beforeVal > 0 && count == 0) {
            overflowedToZero = true;
        }
    }

    function echidna_count_never_wraps_to_zero() public view returns (bool) {
        return !overflowedToZero;
    }
}
""",
    },
    {
        "name": "SB_IntegerOverflowMinimal",
        "src_rel": "arithmetic/integer_overflow_minimal.sol",
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "contract": "SBIntOverflowMinimalHarness",
        "property_name": "echidna_count_bounded",
        "dep_type": "arithmetic_sub_underflow",
        "harness_code": """pragma solidity ^0.4.24;
import "./integer_overflow_minimal.sol";

contract SBIntOverflowMinimalHarness is IntegerOverflowMinimal {
    function echidna_count_bounded() public view returns (bool) {
        return count <= 1;
    }
}
""",
    },
    {
        "name": "SB_OverflowSimpleAdd",
        "src_rel": "arithmetic/overflow_simple_add.sol",
        "solc_version": "0.4.25",
        "solc_bin": SOLC_0425,
        "contract": "SBOverflowSimpleAddHarness",
        "property_name": "echidna_balance_never_zero",
        "dep_type": "arithmetic_simple_add_overflow",
        "harness_code": """pragma solidity 0.4.25;
import "./overflow_simple_add.sol";

contract SBOverflowSimpleAddHarness is Overflow_Add {
    function echidna_balance_never_zero() public view returns (bool) {
        return balance >= 1;
    }
}
""",
    },
    {
        "name": "SB_OverflowSingleTx",
        "src_rel": "arithmetic/overflow_single_tx.sol",
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "contract": "SBOverflowSingleTxHarness",
        "property_name": "echidna_count_stays_nonzero_bounded",
        "dep_type": "multi_func_arithmetic_state_overflow",
        "harness_code": """pragma solidity ^0.4.24;
import "./overflow_single_tx.sol";

contract SBOverflowSingleTxHarness is IntegerOverflowSingleTransaction {
    function echidna_count_stays_nonzero_bounded() public view returns (bool) {
        return count > 0 && count < (1 << 200);
    }
}
""",
    },
    {
        "name": "SB_FibonacciBalance",
        "src_rel": "access_control/FibonacciBalance.sol",
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "contract": "SBFibonacciHarness",
        "property_name": "echidna_lib_start_not_hijacked",
        "dep_type": "delegatecall_storage_collision",
        "harness_code": """pragma solidity ^0.4.24;
import "./FibonacciBalance.sol";

contract SBFibonacciHarness {
    FibonacciLib public lib;
    FibonacciBalance public target;
    bool public drained;

    function init() public payable {
        require(address(target) == address(0) && msg.value >= 2 ether);
        lib = new FibonacciLib();
        target = (new FibonacciBalance).value(msg.value)(address(lib));
    }

    function callWithdraw() public {
        require(address(target) != address(0));
        uint256 b = address(target).balance;
        target.withdraw();
        if (address(target).balance < b) {
            drained = true;
        }
    }

    function() public payable {}

    function echidna_lib_start_not_hijacked() public view returns (bool) {
        return !drained;
    }
}
""",
    },
    {
        "name": "SB_GuessRandomNumber",
        "src_rel": "bad_randomness/guess_the_random_number.sol",
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "contract": "SBGuessRandomHarness",
        "property_name": "echidna_challenge_not_completed",
        "dep_type": "deterministic_block_randomness_guess",
        "harness_code": """pragma solidity ^0.4.24;
import "./guess_the_random_number.sol";

contract SBGuessRandomHarness {
    GuessTheRandomNumberChallenge public challenge;

    function initChallenge() public payable {
        require(address(challenge) == address(0) && msg.value == 1 ether);
        challenge = (new GuessTheRandomNumberChallenge).value(1 ether)();
    }

    function guessNumber(uint8 n) public payable {
        require(address(challenge) != address(0) && msg.value == 1 ether);
        challenge.guess.value(1 ether)(n);
    }

    function() public payable {}

    function echidna_challenge_not_completed() public view returns (bool) {
        if (address(challenge) == address(0)) {
            return true;
        }
        return !challenge.isComplete();
    }
}
""",
    },
    {
        "name": "SB_FindThisHash",
        "src_rel": "front_running/FindThisHash.sol",
        "solc_version": "0.4.24",
        "solc_bin": SOLC_0424,
        "contract": "SBFindThisHashHarness",
        "property_name": "echidna_hash_puzzle_unsolved",
        "dep_type": "keccak256_preimage_semantic_puzzle",
        "harness_code": """pragma solidity ^0.4.24;
import "./FindThisHash.sol";

contract SBFindThisHashHarness is FindThisHash {
    bool public solved;

    function solvePuzzle(string solution) public {
        require(hash == keccak256(abi.encodePacked(solution)));
        solved = true;
    }

    function echidna_hash_puzzle_unsolved() public view returns (bool) {
        return !solved;
    }
}
""",
    },
]


def step1_prepare() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "func/功能") + ":" + env.get("PYTHONPATH", "")
    (RESULT_DIR / "分析产物").mkdir(parents=True, exist_ok=True)
    prop_ids: dict[str, str] = {}

    for spec in BATCH2_SPECS:
        name = spec["name"]
        sol_dir = ROOT / "sol/单合约测试" / name
        sol_dir.mkdir(parents=True, exist_ok=True)
        src = SB_DS / spec["src_rel"]
        shutil.copy2(src, sol_dir / src.name)
        target_sol = sol_dir / "Harness.sol"
        target_sol.write_text(spec["harness_code"], encoding="utf-8")

        cfg = {
            "schema_version": 1,
            "project_name": name,
            "v2_enabled": True,
            "source": {
                "repository": "https://github.com/smartbugs/smartbugs-curated",
                "commit": "230e649123477eff332742a59a1c7cc6dc286cab",
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
            "harness": {"source": "Harness.sol", "contract": spec["contract"]},
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

        print(f"[PREP-B2] {name} ...", flush=True)
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


def step2_probe_and_merge_100(prop_ids: dict[str, str]) -> None:
    sys.path[:0] = [
        str(ROOT / ".tools/phase43-runtime-py311"),
        str(ROOT / "deepseek"),
        str(ROOT / "func/功能"),
    ]
    from 属性种子上下文 import load_project_context
    from 种子验证 import AnvilSession, inspect_initial_state, run_echidna

    probe_root = RESULT_DIR / "Native摸底_19外部"
    if probe_root.exists():
        shutil.rmtree(probe_root)
    probe_root.mkdir(parents=True, exist_ok=True)

    b2_rows = []
    for idx, spec in enumerate(BATCH2_SPECS, start=1):
        name = spec["name"]
        pid = prop_ids[name]
        pname = spec["property_name"]
        row: dict[str, Any] = {
            "group": "A1_PublicClassic",
            "source_type": "smartbugs-curated",
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
                f"[{idx:02d}/19] {name}: actions={len(actions)} init={pval} "
                f"native_ce={row['native_falsified']} t={row['native_elapsed_seconds']}s "
                f"instr={row['native_unique_instructions']} -> {row['admission_status']}",
                flush=True,
            )
        except Exception as exc:
            row["admission_status"] = "failed"
            row["error"] = f"{type(exc).__name__}: {str(exc)[:400]}"
            print(f"[{idx:02d}/19] {name}: ERR {row['error']}", flush=True)
        b2_rows.append(row)

    (RESULT_DIR / "external_19_probe.json").write_text(
        json.dumps(b2_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Merge into unified 100-task formal manifest!
    m2_20 = json.loads((ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/M2正式基准集/dataset_manifest_m2.json").read_text(encoding="utf-8"))
    ext_15 = json.loads((RESULT_DIR / "external_15_probe.json").read_text(encoding="utf-8"))
    real_all = json.loads((ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/M2正式基准集/real_projects_all_properties_audit.json").read_text(encoding="utf-8"))

    unified: list[dict[str, Any]] = []
    # 1. A1 (8 from M2 + 15 from Batch1 + 19 from Batch2 = 42)
    for r in m2_20:
        if r["group"] == "A1_PublicClassic":
            unified.append({**r, "source_type": "public-classic"})
    for r in ext_15:
        if r.get("admission_status") == "admitted":
            unified.append(r)
    for r in b2_rows:
        if r.get("admission_status") == "admitted":
            unified.append(r)

    # 2. A2 (6 DeFi controlled ablation)
    for r in m2_20:
        if r["group"] == "A2_DeFiStateful":
            unified.append({**r, "source_type": "defi-controlled-ablation"})

    # 3. B (52 real open-source multi-contract properties from 6 verified projects)
    verified_real = {"Request", "Immutable", "Hokusai", "BeeStorage", "Kink", "OpenNFTs"}
    for r in real_all:
        if r["project"] in verified_real and r.get("admitted"):
            unified.append({
                "group": "B_RealMultiContract",
                "source_type": "real-open-source-protocol",
                "project": r["project"],
                "property_id": r["property_id"],
                "property_name": r["property_name"],
                "candidate_action_count": r["candidate_action_count"],
                "anvil_initial_property": r["anvil_initial_property"],
                "admission_status": "admitted",
            })

    for i, item in enumerate(unified, start=1):
        item["global_task_id"] = f"T{i:03d}"

    manifest_100 = RESULT_DIR / "dataset_manifest_100.json"
    manifest_100.write_text(json.dumps(unified, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    by_group = {}
    for item in unified:
        by_group[item["group"]] = by_group.get(item["group"], 0) + 1
    print(f"\n=== UNIFIED M2-PLUS MANIFEST: TOTAL={len(unified)} | {by_group} ===", flush=True)
    print(f"Saved to {manifest_100}", flush=True)


def main() -> None:
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    ids_path = RESULT_DIR / "external_19_prop_ids.json"
    if phase == "prep":
        ids = step1_prepare()
        ids_path.write_text(json.dumps(ids, indent=2), encoding="utf-8")
    elif phase == "probe":
        ids = json.loads(ids_path.read_text(encoding="utf-8"))
        step2_probe_and_merge_100(ids)
    else:
        ids = step1_prepare()
        ids_path.write_text(json.dumps(ids, indent=2), encoding="utf-8")
        subprocess.run([PY311, str(Path(__file__).resolve()), "probe"], check=True)


if __name__ == "__main__":
    main()
