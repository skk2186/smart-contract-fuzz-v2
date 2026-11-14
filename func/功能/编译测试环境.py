#!/usr/bin/env python3
"""用 Crytic Compile 编译原生属性 Harness，提取 ABI 与部署字节码。"""

import argparse
import json
import os
import tempfile
from pathlib import Path

from crytic_compile import CryticCompile


ROOT = Path(__file__).resolve().parents[2]
SOLC = os.environ.get("SOLC_BIN", "solc")
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
    "BeeStorage": {
        "target": "sol/真实项目/BeeStorage/src/echidna/EchidnaSystemHarness.sol",
        "contract": "EchidnaSystemHarness",
        "remaps": "@openzeppelin/contracts/=sol/真实项目/依赖/OpenZeppelin482/contracts/",
        "solc_version": "0.8.20",
    },
    "Drips": {
        "target": "sol/真实项目/DripsSCFuzzBench",
        "contract": "Echidna",
        "remaps": None,
        "solc_version": "0.8.20",
        "foundry": True,
    },
    "Kink": {
        "target": "sol/真实项目/Kink/echidna/KinkPoolEchidna.sol",
        "contract": "KinkPoolEchidna",
        "remaps": "@openzeppelin/contracts/=sol/真实项目/依赖/OpenZeppelin550/contracts/",
        "solc_version": "0.8.20",
        "solc_args": "--optimize --via-ir",
    },
}


def compile_project(name, solc=SOLC):
    config = PROJECTS[name]
    os.environ["SOLC_VERSION"] = config["solc_version"]
    compile_options = {"cwd": str(ROOT)}
    if solc:
        compile_options["solc"] = solc
    if config.get("remaps"):
        compile_options["solc_remaps"] = config["remaps"]
    if config.get("solc_args"):
        compile_options["solc_args"] = config["solc_args"]
    previous_path = os.environ.get("PATH", "")
    if config.get("foundry"):
        os.environ["PATH"] = str(ROOT / ".tools/foundry/bin") + os.pathsep + previous_path
    temporary_build = tempfile.TemporaryDirectory(prefix=f"crytic-{name}-") \
        if config.get("foundry") else None
    environment_keys = ("FOUNDRY_OUT", "FOUNDRY_CACHE_PATH")
    previous_environment = {key: os.environ.get(key) for key in environment_keys}
    if temporary_build is not None:
        os.environ["FOUNDRY_OUT"] = str(Path(temporary_build.name) / "out")
        os.environ["FOUNDRY_CACHE_PATH"] = str(Path(temporary_build.name) / "cache")
    try:
        result = CryticCompile(config["target"], **compile_options)
    finally:
        os.environ["PATH"] = previous_path
        for key, value in previous_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if temporary_build is not None:
            temporary_build.cleanup()
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
    parser.add_argument("--solc", default=SOLC,
                        help="Solidity 编译器可执行文件；可用 SOLC_BIN 设置默认值")
    parser.add_argument("--output-dir", default=".tools/results",
                        help="ABI 与字节码输出目录，默认使用本地结果目录")
    args = parser.parse_args()
    names = PROJECTS if args.project == "all" else [args.project]
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        result = compile_project(name, solc=args.solc)
        output = output_dir / f"{name}-Harness编译.json"
        output.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        print(name, "ABI", len(result["abi"]), "bytecode_bytes",
              (len(result["bytecode"]) - 2) // 2, flush=True)


if __name__ == "__main__":
    main()
