#!/usr/bin/env python3
"""对 Phase32 上游源码和编译配置生成可复核 SHA-256 清单。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-20261120"
CONFIGS = ROOT / "func/测试过程/SCFuzzBench公开项目接入/项目配置"
INCLUDE_NAMES = {"foundry.toml", "foundry.lock", ".gitmodules", "echidna.yaml",
                 "medusa.json", "remappings.txt"}
EXCLUDED = {"out", "cache", "broadcast", "node_modules", ".git"}


def main() -> None:
    projects = []
    for config_path in sorted(CONFIGS.glob("Phase32*.json")):
        config = json.loads(config_path.read_text(encoding="utf-8"))
        root = ROOT / config["source"]["root"]
        files = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or any(part in EXCLUDED for part in path.relative_to(root).parts):
                continue
            if path.suffix != ".sol" and path.name not in INCLUDE_NAMES:
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            files.append({"path": path.relative_to(root).as_posix(), "sha256": digest,
                          "size_bytes": path.stat().st_size})
        canonical = "".join(f"{row['sha256']}  {row['path']}\n" for row in files)
        projects.append({"project": config["project_name"],
                         "repository": config["source"]["repository"],
                         "commit": config["source"]["commit"],
                         "submodules": config["source"].get("submodules", {}),
                         "source_root": config["source"]["root"],
                         "manifest_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
                         "files": files})
    output = RESULTS / "上游源码SHA256清单.json"
    output.write_text(json.dumps({"schema_version": 1, "projects": projects},
                                 ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output.relative_to(ROOT)),
                      "projects": [{"name": p["project"], "files": len(p["files"]),
                                    "manifest_sha256": p["manifest_sha256"]}
                                   for p in projects]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
