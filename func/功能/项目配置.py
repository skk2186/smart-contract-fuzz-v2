#!/usr/bin/env python3
"""按声明式项目配置扩展 V2 项目入口，旧项目继续使用原有配置。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR = ROOT / "func/测试过程/SCFuzzBench公开项目接入/项目配置"


def project_profiles() -> dict[str, dict[str, Any]]:
    """读取已启用的项目配置；未完成接入的冻结候选不会进入 V2 入口。"""
    profiles: dict[str, dict[str, Any]] = {}
    if not PROFILE_DIR.is_dir():
        return profiles
    for path in sorted(PROFILE_DIR.glob("*.json")):
        config = json.loads(path.read_text(encoding="utf-8"))
        if config.get("schema_version") != 1 or config.get("v2_enabled") is not True:
            continue
        name = config["project_name"]
        source_root = config["source"]["root"]
        harness = config["harness"]
        compiler = config["compiler"]
        paths = config["paths"]
        profile = {
            "report": paths["analysis_report"],
            "artifact": paths["compiled_artifact"],
            "source_root": source_root,
            "contract": harness["contract"],
            "target": compiler["target"],
            "solc_version": compiler["version"],
            "solc": compiler.get("solc"),
            "remaps": " ".join(compiler.get("remappings", [])) or None,
            "solc_args": " ".join(compiler.get("extra_args", [])) or None,
            "compile_options": compiler.get("compile_options", {}),
            "foundry": compiler.get("build_system") == "foundry",
            "fuzzer_target": str(ROOT / source_root / harness["source"]),
            "constructor_args": config.get("deployment", {}).get("constructor_args", []),
            "deployment": config.get("deployment", {}),
            "execution": config.get("execution", {}),
            "senders": config.get("actions", {}).get("senders", []),
            "echidna": config.get("echidna", {}),
            "medusa": config.get("medusa", {}),
            "property": config.get("property", {}),
            "profile_path": str(path.relative_to(ROOT)),
            "_raw": config,
        }
        profiles[name] = profile
    return profiles


def register_project_profiles(projects: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """将启用的 JSON 配置合并进旧项目表，不要求改动项目名分支。"""
    for name, config in project_profiles().items():
        projects[name] = config
    return projects


def project_profile(project: str) -> dict[str, Any] | None:
    """返回当前配置文件中的原始配置，旧七项目返回 None。"""
    return project_profiles().get(project, {}).get("_raw")
