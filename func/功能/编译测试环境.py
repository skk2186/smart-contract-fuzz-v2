#!/usr/bin/env python3
"""用 Crytic Compile 编译原生属性 Harness，提取 ABI 与部署字节码。"""

import argparse
import json
import os
from pathlib import Path

from crytic_compile import CryticCompile


ROOT = Path(__file__).resolve().parents[2]
SOLC = "/home/skk/miniconda3/envs/contract-fuzz/bin/solc"
PROJECTS = {
    "Request": {
        "target": "sol/真实项目/Request/src/contracts/test/EchidnaERC20CommerceEscrowWrapper.sol",
        "contract": "EchidnaERC20CommerceEscrowWrapper",
        "remaps": "@openzeppelin/contracts/=sol/真实项目/依赖/OpenZeppelin4/contracts/",
        "solc_version": "0.8.20",
    },
    "Immutable": {
        "target": "sol/真实项目/Immutable/test/token/erc721/fuzz/ERC721PsiV2.Echidna.sol",
        "contract": "ERC721PsiV2Echidna",
        "remaps": ("openzeppelin-contracts-4/=sol/真实项目/依赖/OpenZeppelin4/contracts/ "
                   "openzeppelin-contracts-5/=sol/真实项目/依赖/OpenZeppelin561/contracts/"),
        "solc_version": "0.8.20",
    },
    "HokusaiToken": {
        "target": "sol/真实项目/Hokusai/contracts/echidna/EchidnaHokusaiToken.sol",
        "contract": "EchidnaHokusaiToken",
        "remaps": "@openzeppelin/contracts/=sol/真实项目/依赖/OpenZeppelin4/contracts/",
        "solc_version": "0.8.20",
    },
}


def compile_project(name):
    config = PROJECTS[name]
    os.environ["SOLC_VERSION"] = config["solc_version"]
    result = CryticCompile(config["target"], solc=SOLC,
                           solc_remaps=config["remaps"], cwd=str(ROOT))
    found = []
    for unit in result.compilation_units.values():
        for filename, source_unit in unit.source_units.items():
            if config["contract"] in source_unit.contracts_names:
                found.append((filename, source_unit, unit))
    if len(found) != 1:
        raise ValueError(f"{name}: 预期一个属性 Harness，实际 {len(found)}")
    filename, source_unit, unit = found[0]
    abi = source_unit.abi(config["contract"])
    bytecode = source_unit.bytecode_init(config["contract"])
    if not abi or not bytecode or "__" in bytecode:
        raise ValueError(f"{name}: ABI/字节码缺失或库尚未链接")
    contract_abis = {}
    for compilation_unit in result.compilation_units.values():
        for other_source_unit in compilation_unit.source_units.values():
            for contract_name in other_source_unit.contracts_names:
                try:
                    other_abi = other_source_unit.abi(contract_name)
                except Exception:
                    continue
                if other_abi:
                    contract_abis[contract_name] = other_abi
    return {"project": name, "target": config["target"], "contract": config["contract"],
            "source": filename.used,
            "compiler": str(getattr(unit.compiler_version, "version", unit.compiler_version)),
            "abi": abi, "contract_abis": contract_abis,
            "bytecode": "0x" + bytecode.removeprefix("0x")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", choices=list(PROJECTS) + ["all"])
    args = parser.parse_args()
    names = PROJECTS if args.project == "all" else [args.project]
    for name in names:
        result = compile_project(name)
        output = ROOT / f".tools/results/{name}-Harness编译.json"
        output.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        print(name, "ABI", len(result["abi"]), "bytecode_bytes",
              (len(result["bytecode"]) - 2) // 2, flush=True)


if __name__ == "__main__":
    main()
