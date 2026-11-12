#!/usr/bin/env python3
"""从固定版本源码中复制 Solidity 导入闭包，避免把整个项目放入样本目录。"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path


IMPORT = re.compile(
    r"\bimport\s+(?:[^;]*?\bfrom\s*)?[\"']([^\"']+)[\"'](?:\s+as\s+\w+)?\s*;",
    re.DOTALL,
)


def inside(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"源码路径越界或缺少映射：{path}；根目录：{root}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--destination-root", required=True, type=Path)
    parser.add_argument("--entry", required=True, action="append", help="相对主源码根的入口文件，可重复")
    parser.add_argument("--map", action="append", default=[],
                        help="包映射 PREFIX=SOURCE_ROOT=DESTINATION_ROOT，可重复")
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    destination_root = args.destination_root.resolve()
    mappings = []
    for value in args.map:
        parts = value.split("=", 2)
        if len(parts) != 3 or not parts[0]:
            parser.error(f"映射格式应为 PREFIX=SOURCE_ROOT=DESTINATION_ROOT：{value}")
        mappings.append((parts[0], Path(parts[1]).resolve(), Path(parts[2]).resolve()))
    mappings.sort(key=lambda item: len(item[0]), reverse=True)

    pending = [(source_root / entry, source_root, destination_root)
               for entry in args.entry]
    seen: set[Path] = set()
    copied: list[tuple[Path, str]] = []
    missing: list[str] = []
    while pending:
        source, owner_root, output_root = pending.pop()
        source = source.resolve()
        if source in seen:
            continue
        seen.add(source)
        relative = inside(source, owner_root)
        if not source.is_file():
            missing.append(str(source))
            continue
        contents = source.read_bytes()
        target = output_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != contents:
            raise ValueError(f"目标文件已存在且内容不同：{target}")
        target.write_bytes(contents)
        copied.append((target, hashlib.sha256(contents).hexdigest()))
        for imported in IMPORT.findall(contents.decode("utf-8")):
            if imported.startswith("."):
                pending.append((source.parent / imported, owner_root, output_root))
            else:
                match = next((m for m in mappings if imported.startswith(m[0])), None)
                if match is None:
                    missing.append(f"{source}: 未映射的导入 {imported}")
                else:
                    prefix, package_root, package_output = match
                    pending.append((package_root / imported[len(prefix):], package_root,
                                    package_output))
    for target, digest in sorted(copied):
        print(f"{digest}  {target}")
    if missing:
        print("无法解析的导入：", file=sys.stderr)
        for item in sorted(set(missing)):
            print(f"  {item}", file=sys.stderr)
        return 1
    print(f"已复制 {len(copied)} 个 Solidity 文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
