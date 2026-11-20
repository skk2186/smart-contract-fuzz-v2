#!/usr/bin/env python3
"""把冻结样本的 Foundry 输出整理为 V2 Anvil 回放器所需的 ABI/bytecode 结构。"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-20261120"
SPECS = [
    ("sol/真实项目/PigfoxRWATokenDemo", "Properties.sol/Properties.json",
     "RWA-Properties-artifact.json"),
    ("sol/真实项目/ReconVaultFuzzExample", "CryticTester.sol/CryticTester.json",
     "Vault-CryticTester-artifact.json"),
]


def main() -> None:
    for source_root, artifact_relative, output_name in SPECS:
        root = ROOT / source_root
        target = json.loads((root / "out" / artifact_relative).read_text(encoding="utf-8"))
        contract_abis = {}
        for path in sorted((root / "out").rglob("*.json")):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (isinstance(item.get("abi"), list)
                    and isinstance(item.get("bytecode"), dict)
                    and item["bytecode"].get("object")):
                contract_abis[path.stem] = item["abi"]
        normalized = {
            "contractName": target.get("contractName") or Path(artifact_relative).stem,
            "sourceName": target.get("sourceName"),
            "abi": target["abi"],
            "bytecode": target["bytecode"]["object"],
            "deployedBytecode": target.get("deployedBytecode", {}).get("object"),
            "compiler": {"version": "0.8.28", "build_system": "Foundry"},
            "contract_abis": contract_abis,
        }
        destination = RESULTS / output_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        print(json.dumps({"artifact": str(destination.relative_to(ROOT)),
                          "contract": normalized["contractName"],
                          "abi_entries": len(normalized["abi"]),
                          "indexed_contract_abis": len(contract_abis)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
