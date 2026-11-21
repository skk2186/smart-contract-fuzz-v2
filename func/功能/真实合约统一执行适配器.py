#!/usr/bin/env python3
"""统一准备固定真实项目，并将 Foundry/Anvil 结果映射为 V2 交易反馈。"""

from __future__ import annotations

import hashlib
import base64
import json
import os
import re
import shutil
import subprocess
import tarfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parents[2]
HEVM = "0x7109709ECfa91a80626fF3989D68f67F5b1DD12D"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _run(command: list[str], cwd: Path, env: Optional[dict[str, str]] = None,
         timeout: int = 120, log_path: Optional[Path] = None) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=str(cwd), env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout, check=False)
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(result.stdout, encoding="utf-8")
    return result


def _git(project: Path, *args: str, timeout: int = 120) -> str:
    result = _run(["git", "-C", str(project), *args], ROOT, timeout=timeout)
    if result.returncode:
        raise RuntimeError("git " + " ".join(args) + " failed: " + result.stdout[-3000:])
    return result.stdout.strip()


def _submodules(project: Path) -> list[dict[str, str]]:
    result = _run(["git", "-C", str(project), "submodule", "status", "--recursive"], ROOT)
    if result.returncode:
        raise RuntimeError("git submodule status failed: " + result.stdout[-3000:])
    text = result.stdout
    rows = []
    for line in text.splitlines():
        match = re.match(r"^([-+U ])([0-9a-f]{40})\s+(\S+)(?:\s+\(([^)]*)\))?$", line)
        if match:
            rows.append({"marker": match.group(1), "commit": match.group(2),
                         "path": match.group(3), "label": match.group(4) or ""})
    return rows


def _ls_files(project: Path) -> list[Path]:
    result = subprocess.run(["git", "-C", str(project), "ls-files", "-z"], cwd=str(ROOT),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace")[-2000:])
    files = []
    for raw in result.stdout.split(b"\0"):
        if raw:
            path = project / Path(os.fsdecode(raw))
            if path.is_file() or path.is_symlink():
                files.append(path)
    return files


def _inventory(project: Path, submodules: list[dict[str, str]]) -> tuple[list[tuple[str, Path, str]], str]:
    files: dict[str, tuple[Path, str]] = {}
    repositories = [(project, "")] + [(project / row["path"], row["path"]) for row in submodules]
    for repository, prefix in repositories:
        if not repository.is_dir():
            continue
        for path in _ls_files(repository):
            rel = Path(prefix, path.relative_to(repository)).as_posix() if prefix else path.relative_to(project).as_posix()
            files[rel] = (path, sha256_file(path))
    inventory = [(name, path, digest) for name, (path, digest) in files.items()]
    h = hashlib.sha256()
    for name, _, digest in sorted(inventory):
        h.update(name.encode("utf-8") + b"\0" + digest.encode("ascii") + b"\n")
    return sorted(inventory, key=lambda row: row[0]), h.hexdigest()


def _make_cache(cache_dir: Path, inventory: list[tuple[str, Path, str]],
                tree_hash: str, commit: str, submodules: list[dict[str, str]],
                archive_dependencies: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive_dependencies = archive_dependencies or []
    archive = cache_dir / "source-and-dependencies.tar.gz"
    metadata_path = cache_dir / "cache.json"
    expected_dependencies = [{"path": row["path"], "commit": row["commit"]} for row in submodules]
    expected_archives = [{"path": row["path"], "name": row["name"],
                          "version": row["version"], "integrity": row["integrity"]}
                         for row in archive_dependencies]
    reused = False
    if archive.is_file() and metadata_path.is_file():
        metadata = read_json(metadata_path)
        reused = (metadata.get("archive_sha256") == sha256_file(archive)
                  and metadata.get("source_tree_sha256") == tree_hash
                  and metadata.get("upstream_commit") == commit
                  and metadata.get("dependencies") == expected_dependencies
                  and metadata.get("archive_dependencies", []) == expected_archives)
    if not reused:
        temp = archive.with_suffix(".tmp")
        with tarfile.open(temp, "w:gz") as tar:
            for relative, path, _ in inventory:
                tar.add(path, arcname=relative, recursive=False)
        temp.replace(archive)
        write_json(metadata_path, {"upstream_commit": commit, "source_tree_sha256": tree_hash,
                                   "dependencies": expected_dependencies,
                                   "archive_dependencies": expected_archives,
                                   "file_count": len(inventory), "archive_sha256": sha256_file(archive)})
    metadata = read_json(metadata_path)
    workspace = cache_dir / "workspace"
    marker = workspace / ".phase40-cache.json"
    workspace.mkdir(parents=True, exist_ok=True)
    workspace_reused = False
    if marker.is_file():
        try:
            marker_data = read_json(marker)
            workspace_reused = (marker_data.get("source_tree_sha256") == tree_hash
                                and marker_data.get("archive_dependencies", []) == expected_archives
                                and all((workspace / relative).is_file()
                                        and sha256_file(workspace / relative) == digest
                                        for relative, _, digest in inventory))
        except Exception:
            pass
    if not workspace_reused:
        for child in workspace.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        with tarfile.open(archive, "r:gz") as tar:
            root = workspace.resolve()
            for member in tar.getmembers():
                dest = (workspace / member.name).resolve()
                if dest != root and root not in dest.parents:
                    raise RuntimeError("unsafe cache archive member: " + member.name)
            tar.extractall(workspace)
        write_json(marker, {"source_tree_sha256": tree_hash, "upstream_commit": commit,
                            "archive_dependencies": expected_archives})
    if not all((workspace / relative).is_file() and sha256_file(workspace / relative) == digest
               for relative, _, digest in inventory):
        raise RuntimeError("restored cache workspace failed tracked-file SHA-256 verification")
    return {"archive": str(archive), "archive_sha256": metadata["archive_sha256"],
            "workspace": str(workspace), "source_tree_sha256": tree_hash,
            "file_count": len(inventory), "reused": reused,
            "workspace_reused": workspace_reused}


def _verify_sri(path: Path, integrity: str) -> bool:
    match = re.fullmatch(r"(sha256|sha384|sha512)-([A-Za-z0-9+/=]+)", integrity)
    if not match:
        raise ValueError("unsupported package integrity string: " + integrity)
    algorithm, expected = match.groups()
    actual = base64.b64encode(hashlib.new(algorithm, path.read_bytes()).digest()).decode("ascii")
    return actual == expected


def _restore_archive_dependencies(workspace: Path, cache_dir: Path,
                                  dependencies: list[dict[str, Any]],
                                  output: Path, retry_failed: bool = False
                                  ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    restored, missing = [], []
    package_cache = cache_dir / "packages"
    package_cache.mkdir(parents=True, exist_ok=True)
    for item in dependencies:
        relative = Path(item["path"])
        target = (workspace / relative).resolve()
        root = workspace.resolve()
        if target != root and root not in target.parents:
            raise ValueError("package dependency path escapes workspace: " + str(relative))
        archive = package_cache / (item["name"].replace("/", "_") + "-" + item["version"] + ".tgz")
        failure_marker = archive.with_suffix(".failure.json")
        log = output / ("01b-package-" + re.sub(r"[^A-Za-z0-9_.-]+", "_", item["name"]) + ".log")
        attempt = "reuse verified cached archive; otherwise fetch the exact HTTPS URL once and verify SRI"
        try:
            has_verified_archive = archive.is_file() and _verify_sri(archive, item["integrity"])
            if not has_verified_archive and failure_marker.is_file() and not retry_failed:
                previous = read_json(failure_marker)
                if previous.get("integrity") == item["integrity"]:
                    raise RuntimeError("previous fixed-archive attempt failed; retry requires explicit authorization: "
                                       + str(previous.get("error")))
            if not has_verified_archive:
                archive.unlink(missing_ok=True)
                if not item["resolved"].startswith("https://"):
                    raise ValueError("package archive URL must use HTTPS")
                with urllib.request.urlopen(item["resolved"], timeout=60) as response, archive.open("wb") as stream:
                    shutil.copyfileobj(response, stream)
                if not _verify_sri(archive, item["integrity"]):
                    archive.unlink(missing_ok=True)
                    raise ValueError("downloaded archive failed lockfile SRI verification")
            temp = package_cache / ("extract-" + re.sub(r"[^A-Za-z0-9_.-]+", "_", item["name"]))
            if temp.exists():
                shutil.rmtree(temp)
            temp.mkdir(parents=True)
            with tarfile.open(archive, "r:gz") as tar:
                members = tar.getmembers()
                for member in members:
                    parts = Path(member.name)
                    if parts.is_absolute() or ".." in parts.parts or member.issym() or member.islnk():
                        raise ValueError("unsafe package archive member: " + member.name)
                tar.extractall(temp)
            extracted = temp / "package"
            metadata = read_json(extracted / "package.json")
            if metadata.get("name") != item["name"] or metadata.get("version") != item["version"]:
                raise ValueError("package metadata does not match locked name/version")
            reused_target = False
            if target.is_dir():
                try:
                    current = read_json(target / "package.json")
                    reused_target = current.get("name") == item["name"] and current.get("version") == item["version"]
                except Exception:
                    pass
            if not reused_target:
                if target.exists():
                    shutil.rmtree(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(extracted, target, symlinks=True)
            shutil.rmtree(temp)
            result = {"path": str(relative), "name": item["name"], "version": item["version"],
                      "integrity": item["integrity"], "archive_sha256": sha256_file(archive),
                      "status": "ready", "reused": reused_target, "attempt": attempt}
            failure_marker.unlink(missing_ok=True)
            write_json(output / ("01b-package-" + re.sub(r"[^A-Za-z0-9_.-]+", "_", item["name"]) + ".json"), result)
            log.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            restored.append(result)
        except Exception as exc:
            error = "%s: %s" % (type(exc).__name__, exc)
            row = {"path": str(relative), "fixed_sha": item.get("integrity"),
                   "version": item.get("version"), "attempt": attempt, "error": error}
            missing.append(row)
            write_json(failure_marker, {"path": str(relative), "integrity": item.get("integrity"),
                                        "version": item.get("version"), "error": error,
                                        "retry_suppressed_by_default": True})
            write_json(output / ("01b-package-" + re.sub(r"[^A-Za-z0-9_.-]+", "_", item["name"]) + ".json"),
                       {**row, "status": "dependency_blocked"})
            log.write_text(json.dumps({**row, "status": "dependency_blocked"},
                                      ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return restored, missing


def prepare_project(manifest_path: Path, output: Path, restore_missing: bool = True,
                    retry_failed_archives: bool = False,
                    retry_missing_submodules: bool = False) -> dict[str, Any]:
    """核验固定上游和递归依赖；缺失 submodule 仅按 gitlink SHA 尝试一次恢复。"""
    manifest = read_json(manifest_path)
    cfg = manifest["project"]
    source = (ROOT / cfg["source_root"]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cache_dir = ROOT / ".tools/cache/real-contracts" / (cfg["id"] + "-" + cfg["commit"])
    submodule_failure_marker = cache_dir / "submodule-restore.failure.json"
    restoration = None
    try:
        commit = _git(source, "rev-parse", "HEAD")
        if commit != cfg["commit"]:
            raise RuntimeError("upstream commit mismatch: expected %s got %s" % (cfg["commit"], commit))
        submodules = _submodules(source)
        expected = {item["path"]: item["commit"] for item in manifest.get("dependencies", [])}
        problems = [row for row in submodules if row["marker"] in "-U+" or
                    expected.get(row["path"], row["commit"]) != row["commit"] or
                    not (source / row["path"]).is_dir()]
        restore_error = None
        if problems and restore_missing:
            previous_failure = (read_json(submodule_failure_marker)
                                if submodule_failure_marker.is_file() else None)
            if previous_failure and not retry_missing_submodules:
                restore_error = previous_failure.get("error", "previous fixed submodule restore failed")
                restoration = {"status": "retry_suppressed", "marker": str(submodule_failure_marker),
                               "previous_attempt": previous_failure.get("attempt")}
            else:
                command = ["git", "-C", str(source), "submodule", "update", "--init", "--recursive", "--checkout"]
                log = output / "01a-submodule-restore.log"
                try:
                    result = _run(command, ROOT, timeout=240, log_path=log)
                    restoration = {"command": command, "log": str(log), "returncode": result.returncode}
                    if result.returncode:
                        restore_error = result.stdout[-3000:]
                    submodules = _submodules(source)
                    problems = [row for row in submodules if row["marker"] in "-U+" or
                                expected.get(row["path"], row["commit"]) != row["commit"] or
                                not (source / row["path"]).is_dir()]
                    if problems:
                        restore_error = restore_error or "fixed submodule restore completed but required paths remain missing or mismatched"
                        write_json(submodule_failure_marker, {
                            "attempt": "git submodule update --init --recursive --checkout",
                            "missing_paths": [{"path": row["path"],
                                               "fixed_sha": expected.get(row["path"], row["commit"])}
                                              for row in problems],
                            "error": restore_error, "retry_suppressed_by_default": True})
                    else:
                        submodule_failure_marker.unlink(missing_ok=True)
                except Exception as exc:
                    restore_error = "%s: %s" % (type(exc).__name__, exc)
                    write_json(submodule_failure_marker, {
                        "attempt": "git submodule update --init --recursive --checkout",
                        "missing_paths": [{"path": row["path"],
                                           "fixed_sha": expected.get(row["path"], row["commit"])}
                                          for row in problems],
                        "error": restore_error, "retry_suppressed_by_default": True})
        if problems:
            missing = [{"path": row["path"], "fixed_sha": expected.get(row["path"], row["commit"]),
                        "attempt": "git submodule update --init --recursive --checkout",
                        "error": restore_error or "submodule missing or SHA mismatch"} for row in problems]
            result = {"status": "dependency_blocked", "project_id": cfg["id"],
                      "expected_commit": cfg["commit"], "actual_commit": commit,
                      "missing_paths": missing, "dependencies": submodules,
                      "restore": restoration}
        else:
            inventory, source_hash = _inventory(source, submodules)
            expected_hash = cfg.get("source_tree_sha256")
            if expected_hash and source_hash != expected_hash:
                raise RuntimeError("source tree SHA-256 mismatch: expected %s got %s" % (expected_hash, source_hash))
            if not expected_hash:
                cfg["source_tree_sha256"] = source_hash
            lockfile_results = []
            for lock in manifest.get("lockfiles", []):
                lock_path = (source / lock["path"]).resolve()
                if source not in lock_path.parents or not lock_path.is_file():
                    raise RuntimeError("locked dependency manifest missing: " + lock["path"])
                actual_lock_sha = sha256_file(lock_path)
                if actual_lock_sha != lock["sha256"]:
                    raise RuntimeError("dependency lockfile SHA-256 mismatch for %s: expected %s got %s" %
                                       (lock["path"], lock["sha256"], actual_lock_sha))
                lockfile_results.append({"path": lock["path"], "sha256": actual_lock_sha,
                                         "status": "verified"})
            cache_name = cfg["id"] + "-" + cfg["commit"]
            cache = _make_cache(cache_dir,
                                inventory, source_hash, commit, submodules,
                                manifest.get("archive_dependencies", []))
            restored_archives, missing_archives = _restore_archive_dependencies(
                Path(cache["workspace"]), ROOT / ".tools/cache/real-contracts" / cache_name,
                manifest.get("archive_dependencies", []), output, retry_failed_archives)
            result = {"status": "dependency_blocked" if missing_archives else "ready",
                      "project_id": cfg["id"], "source_root": str(source),
                      "expected_commit": cfg["commit"], "actual_commit": commit,
                      "source_tree_sha256": source_hash, "tracked_file_count": len(inventory),
                      "dependencies": submodules, "lockfiles": lockfile_results,
                      "archive_dependencies": restored_archives,
                      "missing_paths": missing_archives,
                      "cache": cache, "restore": restoration}
    except Exception as exc:
        result = {"status": "execution_failed", "project_id": cfg.get("id"),
                  "expected_commit": cfg.get("commit"), "source_root": str(source),
                  "error": "%s: %s" % (type(exc).__name__, exc), "restore": restoration}
    write_json(output / "01-source-dependency-preparation.json", result)
    (output / "01-source-dependency-preparation.log").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def tool_environment(manifest: dict[str, Any], output: Path) -> tuple[dict[str, str], dict[str, str]]:
    output = output.resolve()
    def resolve(value: str) -> str:
        if "/" in value or "\\" in value:
            path = Path(value)
            if not path.is_absolute():
                path = (ROOT / path).resolve()
            if not path.exists():
                raise FileNotFoundError(str(path))
            return str(path)
        found = shutil.which(value)
        if not found:
            raise FileNotFoundError("tool not found: " + value)
        return found
    tools = {name: resolve(manifest["toolchain"][name]) for name in ("forge", "echidna")}
    version = manifest["build"]["solc_version"]
    solc_candidates = [Path.home() / ".solc-select/artifacts" / ("solc-" + version) / ("solc-" + version),
                       Path.home() / ".svm" / version / ("solc-" + version)]
    solc = next((str(path) for path in solc_candidates if path.is_file()), shutil.which("solc"))
    if not solc:
        raise FileNotFoundError("pinned solc %s not installed" % version)
    versions = {}
    for name, path in [("forge", tools["forge"]), ("echidna", tools["echidna"]), ("solc", solc)]:
        check = _run([path, "--version"], ROOT, timeout=20)
        if check.returncode:
            raise RuntimeError(name + " --version failed: " + check.stdout[-1000:])
        versions[name] = check.stdout.strip()
    if version not in versions["solc"]:
        raise RuntimeError("selected solc version does not match " + version)
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(ROOT / ".tools/foundry/bin"),
                                   str(ROOT / ".tools/olympia-venv/bin"), env.get("PATH", "")])
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / ".tools/python"), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    shim_dir = output / "tool-shim"
    shim_dir.mkdir(parents=True, exist_ok=True)
    shim = shim_dir / "solc"
    shim.write_text("#!/bin/sh\nexec " + json.dumps(solc) + " \"$@\"\n", encoding="utf-8")
    shim.chmod(0o755)
    env["PATH"] = str(shim_dir) + os.pathsep + env["PATH"]
    return env, {**tools, "solc": solc, "versions": versions}


@dataclass
class Transaction:
    signature: str
    arguments: list[Any]
    sender: str
    value_wei: str = "0"
    timestamp: Optional[int] = None
    delay_seconds: int = 0
    block_number: Optional[int] = None
    origin: Optional[str] = None


@dataclass
class ExecutionRequest:
    scenario_id: str
    transactions: list[Transaction]
    continue_after_failure: bool = False
    backend_options: dict[str, Any] = field(default_factory=dict)


class ExecutionBackend:
    """统一后端接口：部署、序列执行、属性检查和 V2 反馈转换。"""
    name = "abstract"

    def deploy_target(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    def execute_sequence(self, request: ExecutionRequest) -> dict[str, Any]:
        raise NotImplementedError

    def check_properties(self, request: ExecutionRequest, raw: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def to_v2_feedback(self, raw: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


def _abi_type(signature: str, index: int) -> str:
    try:
        inner = signature[signature.index("(") + 1:signature.rindex(")")]
        if not inner:
            return ""
        types, start, depth = [], 0, 0
        for offset, char in enumerate(inner):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                types.append(inner[start:offset])
                start = offset + 1
        types.append(inner[start:])
        return types[index]
    except Exception:
        raise ValueError("invalid ABI signature " + signature)


def _sol_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _sol_address(value: str) -> str:
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        raise ValueError("invalid address " + value)
    return "address(" + value + ")"


def _sol_value(value: Any, abi_type: str) -> str:
    if re.fullmatch(r"(?:uint|int)(?:[0-9]+)?", abi_type):
        return abi_type + "(" + str(int(value)) + ")"
    if abi_type == "address":
        if isinstance(value, dict) and "storage_address_slot" in value:
            slot = int(value["storage_address_slot"])
            return "address(uint160(uint256(vm.load(address(target), bytes32(uint256(%d))))))" % slot
        return _sol_address(str(value))
    if abi_type == "bool":
        return "true" if value else "false"
    if abi_type == "string":
        return _sol_string(str(value))
    if abi_type == "bytes" or re.fullmatch(r"bytes[1-9][0-9]?", abi_type):
        raw = str(value)
        raw = raw[2:] if raw.startswith("0x") else raw
        if len(raw) % 2 or not re.fullmatch(r"[0-9a-fA-F]*", raw):
            raise ValueError("byte arguments must be hex strings")
        if abi_type != "bytes":
            width = int(abi_type[5:])
            if len(raw) != width * 2:
                raise ValueError("%s requires exactly %d hex characters" % (abi_type, width * 2))
            return abi_type + '(hex"' + raw + '")'
        return 'hex"' + raw + '"'
    raise ValueError("unsupported ABI type " + abi_type)


def _foundry_test_source(manifest: dict[str, Any], request: ExecutionRequest, output_tsv: Path) -> str:
    harness = manifest["harness"]
    contract = harness["contract"]
    import_path = harness.get("import_path", harness["source"])
    deploy = manifest.get("deployment", {})
    deployer = deploy.get("deployer", "")
    ctor_args = deploy.get("constructor_arguments", [])
    ctor_types = deploy.get("constructor_types", [])
    if len(ctor_args) != len(ctor_types):
        raise ValueError("constructor argument/type count mismatch")
    ctor = ", ".join(_sol_value(v, t) for v, t in zip(ctor_args, ctor_types))
    source = [
        "// SPDX-License-Identifier: MIT", "pragma solidity ^0.8.20;",
        "import {" + contract + "} from " + _sol_string(import_path) + ";",
        "interface VmPhase40 {",
        " function prank(address sender) external;", " function prank(address sender, address origin) external;",
        " function warp(uint256 timestamp) external;", " function roll(uint256 number) external;",
        " function load(address target, bytes32 slot) external view returns (bytes32);",
        " function writeFile(string calldata path, string calldata data) external;",
        " function writeLine(string calldata path, string calldata data) external;", "}",
        "contract Phase40ReplayTest {",
        " VmPhase40 private constant vm = VmPhase40(" + HEVM + ");",
        " event Phase40Transaction(uint256 indexed index,address indexed sender,bool success,bytes4 selector,uint256 value,uint256 timestampBefore,uint256 timestampAfter,uint256 blockNumber,uint256 gasEstimate,bytes returnData);",
        " event Phase40Property(uint256 indexed index,string signature,bool success,bytes returnData);",
        " function _hex(bytes memory data) internal pure returns (string memory) {",
        "  bytes16 a = \"0123456789abcdef\"; bytes memory o = new bytes(data.length * 2);",
        "  for (uint256 i; i < data.length; i++) { o[i*2]=a[uint8(data[i])>>4]; o[i*2+1]=a[uint8(data[i])&15]; } return string(o); }",
        " function _uint(uint256 n) internal pure returns (string memory) { if(n==0)return \"0\"; uint256 s; uint256 c=n; while(c!=0){s++;c/=10;} bytes memory b=new bytes(s); while(n!=0){s--;b[s]=bytes1(uint8(48+n%10));n/=10;} return string(b); }",
        " function _address(address a) internal pure returns (string memory) { return string.concat(\"0x\",_hex(abi.encodePacked(a))); }",
        " function _observe(" + contract + " target,string memory path,uint256 index,string memory phase) internal {",
    ]
    for i, observer in enumerate(manifest.get("observers", [])):
        signature = observer["signature"]
        args = observer.get("arguments", [])
        exprs = [_sol_value(value, _abi_type(signature, j)) for j, value in enumerate(args)]
        encoded = "abi.encodeWithSignature(" + _sol_string(signature)
        if exprs:
            encoded += ", " + ", ".join(exprs)
        encoded += ")"
        target = observer["target"]
        if isinstance(target, dict) and "storage_address_slot" in target:
            target_expr = "address(uint160(uint256(vm.load(address(target),bytes32(uint256(%d))))))" % int(target["storage_address_slot"])
        elif target == "harness":
            target_expr = "address(target)"
        else:
            target_expr = _sol_address(str(target))
        source.extend([
            "  (bool o%d,bytes memory d%d)=%s.staticcall(%s);" % (i, i, target_expr, encoded),
            "  vm.writeLine(path,string.concat(\"OBS\\t\",_uint(index),\"\\t\",phase,\"\\t\",%s,\"\\t\",o%d?\"success\":\"error\",\"\\t0x\",_hex(d%d)));" %
            (_sol_string(observer["name"]), i, i),
        ])
    source.extend([" }", " function testPhase40Scenario() public {"])
    if deployer:
        source.append("  vm.prank(" + _sol_address(deployer) + ");")
    source.extend([
        "  " + contract + " target=new " + contract + "(" + ctor + ");",
        "  string memory path=" + _sol_string(str(output_tsv)) + ";",
        "  vm.writeFile(path,\"\");",
        "  vm.writeLine(path,string.concat(\"DEPLOY\\t\",_address(address(target)),\"\\t\",%s));" % _sol_string(deployer),
        "  bool allPropertiesPass=true;",
    ])
    if not request.continue_after_failure:
        source.append("  bool sequenceAlive=true;")
    for i, tx in enumerate(request.transactions):
        prefix = "t%d_" % i
        indent = "  "
        if not request.continue_after_failure:
            source.append("  if(sequenceAlive){")
            indent = "   "
        source.append(indent + "uint256 %sbefore=block.timestamp;" % prefix)
        source.append(indent + "_observe(target,path,%d,\"before\");" % (i + 1))
        if tx.timestamp is not None:
            source.append(indent + "vm.warp(%d);" % tx.timestamp)
        elif tx.delay_seconds:
            source.append(indent + "vm.warp(block.timestamp+%d);" % tx.delay_seconds)
        if tx.block_number is not None:
            source.append(indent + "vm.roll(%d);" % tx.block_number)
        source.append(indent + "uint256 %satCall=block.timestamp;" % prefix)
        if tx.origin:
            source.append(indent + "vm.prank(%s,%s);" % (_sol_address(tx.sender), _sol_address(tx.origin)))
        else:
            source.append(indent + "vm.prank(%s);" % _sol_address(tx.sender))
        abi_args = [_sol_value(value, _abi_type(tx.signature, j)) for j, value in enumerate(tx.arguments)]
        call = "abi.encodeWithSignature(" + _sol_string(tx.signature)
        if abi_args:
            call += ", " + ", ".join(abi_args)
        call += ")"
        value = int(tx.value_wei)
        source.extend([
            indent + "uint256 %sgasBefore=gasleft();" % prefix,
            indent + "(bool %sok,bytes memory %sdata)=address(target).call{value:%d}(%s);" % (prefix, prefix, value, call),
            indent + "uint256 %sgas= %sgasBefore-gasleft();" % (prefix, prefix),
            indent + "uint256 %safter=block.timestamp;" % prefix,
            indent + "_observe(target,path,%d,\"after\");" % (i + 1),
            indent + "emit Phase40Transaction(%d,%s,%sok,bytes4(keccak256(bytes(%s))),%d,%sbefore,%safter,block.number,%sgas,%sdata);" %
            (i + 1, _sol_address(tx.sender), prefix, _sol_string(tx.signature), value, prefix, prefix, prefix, prefix),
            indent + "string memory %stsv=string.concat(\"TX\\t\",_uint(%d),\"\\t\",%s);" %
            (prefix, i + 1, _sol_string(tx.signature)),
            indent + "%stsv=string.concat(%stsv,\"\\t\",_address(%s),\"\\t\",_uint(%d));" %
            (prefix, prefix, _sol_address(tx.sender), value),
            indent + "%stsv=string.concat(%stsv,\"\\t\",%sok?\"success\":\"reverted\",\"\\t0x\",_hex(%sdata));" %
            (prefix, prefix, prefix, prefix),
            indent + "%stsv=string.concat(%stsv,\"\\t\",_uint(%sgas),\"\\t\",_uint(%sbefore),\"\\t\",_uint(%satCall));" %
            (prefix, prefix, prefix, prefix, prefix),
            indent + "%stsv=string.concat(%stsv,\"\\t\",_uint(%safter),\"\\t\",_uint(block.number));" %
            (prefix, prefix, prefix),
            indent + "vm.writeLine(path,%stsv);" % prefix,
        ])
        if not request.continue_after_failure:
            source.append(indent + "if(!%sok)sequenceAlive=false;" % prefix)
        for j, prop in enumerate(manifest.get("properties", [])):
            signature = prop["signature"]
            values = prop.get("arguments", [])
            prop_args = [_sol_value(value, _abi_type(signature, k)) for k, value in enumerate(values)]
            prop_call = "abi.encodeWithSignature(" + _sol_string(signature)
            if prop_args:
                prop_call += ", " + ", ".join(prop_args)
            prop_call += ")"
            name = "p%d_%d" % (i, j)
            source.extend([
                indent + "(bool %sok,bytes memory %sdata)=address(target).call(%s);" % (name, name, prop_call),
                indent + "emit Phase40Property(%d,%s,%sok,%sdata);" % (i + 1, _sol_string(signature), name, name),
                indent + "vm.writeLine(path,string.concat(\"PROP\\t\",_uint(%d),\"\\t\",%s,\"\\t\",%sok?\"passed\":\"failed\",\"\\t0x\",_hex(%sdata)));" % (i + 1, _sol_string(signature), name, name),
                indent + "if(!%sok)allPropertiesPass=false;" % name,
            ])
        if not request.continue_after_failure:
            source.append("  }")
    source.extend(["  require(allPropertiesPass,\"Phase40 property failure\");", " }", "}"])
    return "\n".join(source) + "\n"


def _foundry_toml(manifest: dict[str, Any], workspace: Path, fixture: Path, output: Path) -> str:
    source_dir = manifest["build"].get("source_directory", "src")
    remappings = [source_dir.rstrip("/") + "/=" +
                  os.path.relpath(workspace / source_dir, fixture).replace("\\", "/") + "/"]
    for mapping in manifest.get("remappings", []):
        alias, target = mapping.split("=", 1)
        path = (workspace / target).resolve()
        remappings.append(alias + "=" + os.path.relpath(path, fixture).replace("\\", "/") + "/")
    return "\n".join([
        # Keep the generated test project's source directory distinct from
        # common upstream import prefixes such as `src/`, so Foundry does not
        # discard a user remapping that targets the frozen project source tree.
        "[profile.default]", 'src = "generated-src"', 'test = "test"', "libs = []",
        'out = ' + _sol_string(str(output / "out")),
        'cache_path = ' + _sol_string(str(output / "cache")),
        'solc_version = ' + _sol_string(manifest["build"]["solc_version"]),
        "auto_detect_solc = false", "offline = true",
        "remappings = [" + ", ".join(_sol_string(item) for item in remappings) + "]",
        "allow_paths = [" + _sol_string(str(workspace.resolve())) + "]",
        "fs_permissions = [{ access = \"write\", path = " + _sol_string(str(output.resolve())) +
        " }, { access = \"write\", path = \"/tmp\" }]",
        "gas_limit = 100000000", "block_gas_limit = 100000000", "",
    ])


class FoundryCheatcodeBackend(ExecutionBackend):
    name = "foundry-cheatcode"

    def __init__(self, manifest: dict[str, Any], workspace: Path, output: Path,
                 env: dict[str, str], forge: str):
        self.manifest, self.workspace, self.output = manifest, workspace.resolve(), output.resolve()
        self.env, self.forge = env, forge

    def deploy_target(self, request: ExecutionRequest) -> dict[str, Any]:
        deploy_request = ExecutionRequest(request.scenario_id + "-deploy-only", [], False)
        raw = self.execute_sequence(deploy_request)
        execution = raw.get("execution") or {}
        return {**execution.get("deployment", {}), "backend": self.name,
                "status": "deployed" if raw.get("status") == "passed" else raw.get("status"),
                "log": raw.get("log"), "harness": self.manifest["harness"]["contract"],
                "exact_contract_type": True, "rpc_impersonation_used": False,
                "error": raw.get("error")}

    def execute_sequence(self, request: ExecutionRequest) -> dict[str, Any]:
        fixture = (self.output / "driver").resolve()
        test_dir = fixture / "test"
        test_dir.mkdir(parents=True, exist_ok=True)
        # Solidity string literals accept ASCII by default; the repository path
        # may contain Chinese directory names. Write through an ASCII-only
        # temporary path, then preserve the artifact beside the run logs.
        tsv = self.output / (request.scenario_id + ".foundry.tsv")
        tsv_runtime = Path("/tmp") / ("phase40-" + hashlib.sha256(
            (str(self.output) + request.scenario_id).encode("utf-8")).hexdigest()[:16] + ".tsv")
        source = test_dir / "Phase40Replay.t.sol"
        try:
            generated_source = _foundry_test_source(self.manifest, request, tsv_runtime)
        except ValueError as exc:
            log = self.output / (request.scenario_id + ".foundry.log")
            message = "unsupported request encoding: %s: %s" % (type(exc).__name__, exc)
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(message + "\n", encoding="utf-8")
            raw = {"backend": self.name, "scenario_id": request.scenario_id,
                   "status": "unsupported_semantics", "error": message,
                   "log": str(log), "driver_source": str(source)}
            write_json(self.output / (request.scenario_id + ".foundry.json"), raw)
            return raw
        source.write_text(generated_source, encoding="utf-8")
        (fixture / "foundry.toml").write_text(_foundry_toml(self.manifest, self.workspace, fixture, self.output), encoding="utf-8")
        command = [self.forge, "test", "--root", str(fixture), "--offline", "--force", "--threads", "1", "--match-contract", "Phase40ReplayTest", "-vv"]
        log = self.output / (request.scenario_id + ".foundry.log")
        completed = _run(command, fixture, self.env, timeout=600, log_path=log)
        if tsv_runtime.is_file():
            shutil.copy2(tsv_runtime, tsv)
            tsv_runtime.unlink()
        execution = _parse_tsv(tsv, request, self.manifest) if tsv.is_file() else None
        trace_complete = bool(execution and execution.get("deployment", {}).get("success")
                              and len(execution.get("transactions", [])) == len(request.transactions)
                              and (execution.get("properties") or not request.transactions))
        status = "passed" if completed.returncode == 0 and trace_complete else "execution_failed"
        missing_trace_reason = None
        if completed.returncode == 0 and not trace_complete:
            missing_trace_reason = "Foundry exited successfully but the generated driver did not produce a complete execution trace."
        raw = {"backend": self.name, "command": command, "returncode": completed.returncode,
               "status": status,
               "log": str(log), "driver_source": str(source), "driver_sha256": sha256_file(source),
               "execution": execution,
               "error": missing_trace_reason if missing_trace_reason else (None if completed.returncode == 0 else completed.stdout[-3000:])}
        write_json(self.output / (request.scenario_id + ".foundry.json"), raw)
        return raw

    def check_properties(self, request: ExecutionRequest, raw: dict[str, Any]) -> dict[str, Any]:
        rows = (raw.get("execution") or {}).get("properties", [])
        return {"status": "passed" if rows and all(row["success"] for row in rows) else "failed",
                "checks": rows}

    def to_v2_feedback(self, raw: dict[str, Any]) -> dict[str, Any]:
        execution = raw.get("execution") or {}
        txs = execution.get("transactions", [])
        properties = execution.get("properties", [])
        return {"backend": self.name, "deployment": execution.get("deployment", {}),
                "transactions": [normalize_transaction(row) for row in txs],
                "properties": properties,
                "state_changes": [change for row in txs for change in row.get("state_changes", [])],
                "state_before": txs[0].get("observations_before", []) if txs else [],
                "state_after": txs[-1].get("observations_after", []) if txs else [],
                "sequence_success": bool(txs) and all(row["status"] == "success" for row in txs),
                "property_checks_passed": bool(properties) and all(row["success"] for row in properties),
                "capabilities": {"msg_sender": True, "tx_origin": True, "internal_prank": True,
                                 "internal_warp": True, "internal_roll": True,
                                 "per_call_success_or_failure": True, "revert_data": True,
                                 "state_observation": True, "mined_transaction_receipts": False,
                                 "transaction_boundaries": False, "gas_used_is_estimate": True,
                                 "rpc_impersonation_used": False},
                "status": raw.get("status"),
                "limitation": "Foundry calls are nested inside one test transaction and do not produce per-call mined receipts."}


def _parse_tsv(path: Path, request: ExecutionRequest, manifest: dict[str, Any]) -> dict[str, Any]:
    deployment = {}
    tx_map: dict[int, dict[str, Any]] = {}
    properties = []
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if fields[0] == "DEPLOY":
            deployment = {"success": True, "target_address": fields[1], "deployer": fields[2]}
        elif fields[0] == "TX":
            idx = int(fields[1])
            row = tx_map.setdefault(idx, {"index": idx, "observations_before": [], "observations_after": []})
            request_tx = request.transactions[idx - 1]
            row.update({"index": idx, "function": fields[2], "sender": fields[3],
                           "arguments": request_tx.arguments, "origin": request_tx.origin,
                           "value_wei": fields[4], "status": fields[5], "return_data": fields[6],
                           "gas_used_estimate": int(fields[7]), "timestamp_before": int(fields[8]),
                           "timestamp_at_call": int(fields[9]), "timestamp_after": int(fields[10]),
                           "block_number": int(fields[11])})
        elif fields[0] == "OBS":
            idx, phase, name, status, raw = int(fields[1]), fields[2], fields[3], fields[4], fields[5]
            definition = next((row for row in manifest.get("observers", []) if row["name"] == name), {})
            observation = {"name": name, "success": status == "success", "raw": raw,
                           "signature": definition.get("signature"),
                           "arguments": definition.get("arguments", []),
                           "output_type": definition.get("output_type")}
            if observation["success"]:
                observation["value"] = decode_observation(raw, definition.get("output_type"))
            tx_map.setdefault(idx, {"index": idx, "observations_before": [], "observations_after": []})[
                "observations_before" if phase == "before" else "observations_after"].append(observation)
        elif fields[0] == "PROP":
            properties.append({"after_transaction": int(fields[1]), "signature": fields[2],
                               "success": fields[3] == "passed", "return_data": fields[4]})
    txs = [tx_map[index] for index in sorted(tx_map) if "function" in tx_map[index]]
    for tx in txs:
        checks = [row for row in properties if row["after_transaction"] == tx["index"]]
        tx["property_checks"] = checks
        tx["target_property"] = (all(row["success"] for row in checks) if checks else None)
        before = {row["name"]: row.get("value") for row in tx.get("observations_before", [])
                  if row.get("success")}
        after = {row["name"]: row.get("value") for row in tx.get("observations_after", [])
                 if row.get("success")}
        tx["state_changes"] = [{"name": name, "before": before.get(name), "after": after.get(name)}
                               for name in sorted(set(before) | set(after))
                               if before.get(name) != after.get(name)]
    return {"scenario_id": request.scenario_id, "backend": "foundry-cheatcode",
            "deployment": deployment, "transactions": txs, "properties": properties,
            "capabilities": {"internal_prank": True, "internal_warp": True,
                             "per_call_status": True, "mined_receipts": False}}


class AnvilRpcBackend(ExecutionBackend):
    """包装 Phase39 的原 Anvil 执行器；不声称支持内部 HEVM cheatcode。"""
    name = "anvil-rpc"

    def __init__(self, python: str, output: Path, env: dict[str, str],
                 spec_template: Optional[Path] = None):
        self.python, self.output, self.env = python, output.resolve(), env
        self.spec_template = spec_template.resolve() if spec_template else None
        self.entry = ROOT / "func/测试过程/SCFuzzBench公开项目接入/Phase39真实合约执行入口.py"

    def _spec_for(self, request: ExecutionRequest) -> Path:
        configured = request.backend_options.get("anvil_spec", self.spec_template)
        if configured is None:
            raise ValueError("Anvil execution requires a fixed Phase39-compatible spec in backend_options['anvil_spec']")
        return Path(configured).resolve()

    def _unsupported(self, request: ExecutionRequest, reason: str, **detail: Any) -> dict[str, Any]:
        raw = {"backend": self.name, "status": "unsupported_semantics",
               "scenario_id": request.scenario_id, "error": reason, **detail}
        log = self.output / (request.scenario_id + ".anvil.log")
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_json(self.output / (request.scenario_id + ".anvil.json"), raw)
        return raw

    def deploy_target(self, request: ExecutionRequest) -> dict[str, Any]:
        deploy_request = ExecutionRequest(request.scenario_id + "-deploy-only", [], False,
                                          request.backend_options)
        raw = self.execute_sequence(deploy_request)
        deployment = ((raw.get("execution") or {}).get("deployment") or {})
        return {**deployment, "backend": self.name, "status": raw.get("status"),
                "log": raw.get("log"), "internal_prank": False,
                "internal_warp": False, "rpc_impersonation_is_native_cheatcode": False}

    def execute_sequence(self, request: ExecutionRequest) -> dict[str, Any]:
        out = (self.output / "anvil" / request.scenario_id).resolve()
        template_path = self._spec_for(request)
        spec = read_json(template_path)
        configured_senders = request.backend_options.get("sender_indices",
                                                        spec.get("sender_indices", {}))
        anvil_transactions = []
        for tx in request.transactions:
            if tx.timestamp is not None or tx.block_number is not None or tx.origin:
                return self._unsupported(
                    request,
                    "Phase39 Anvil runner cannot preserve absolute timestamp, block-number, or distinct tx.origin requests",
                    unsupported_transaction=tx.signature)
            sender_index = configured_senders.get(tx.sender.lower())
            if sender_index is None:
                sender_index = configured_senders.get(tx.sender)
            if sender_index is None:
                return self._unsupported(
                    request, "Anvil sender address has no explicit local-account index mapping",
                    unsupported_sender=tx.sender)
            anvil_transactions.append({"function": tx.signature, "arguments": tx.arguments,
                                       "sender_index": int(sender_index), "value_wei": str(tx.value_wei),
                                       "delay_seconds": int(tx.delay_seconds),
                                       "gas": int(request.backend_options.get("transaction_gas", 12_500_000))})
        spec["transactions"] = anvil_transactions
        spec["continue_after_failure"] = request.continue_after_failure
        generated_spec = self.output / (request.scenario_id + ".anvil-spec.json")
        write_json(generated_spec, spec)
        command = [self.python, str(self.entry), "anvil", "--spec", str(generated_spec), "--output", str(out)]
        log = self.output / (request.scenario_id + ".anvil.log")
        env = dict(self.env)
        # Phase39 can use the fully installed venv packages. Its legacy vendor
        # tree contains partial native wheels that shadow those packages when
        # placed first on PYTHONPATH (for example pydantic_core).
        vendor_python = str((ROOT / ".tools/python").resolve())
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in env.get("PYTHONPATH", "").split(os.pathsep)
            if part and str(Path(part).resolve()) != vendor_python)
        completed = _run(command, ROOT, env, timeout=240, log_path=log)
        result_path = out / "result.json"
        result = read_json(result_path) if result_path.is_file() else None
        raw = {"backend": self.name, "command": command, "returncode": completed.returncode,
               "status": (result or {}).get("status", "execution_failed"),
               "log": str(log), "execution": result}
        write_json(self.output / (request.scenario_id + ".anvil.json"), raw)
        return raw

    def check_properties(self, request: ExecutionRequest, raw: dict[str, Any]) -> dict[str, Any]:
        result = raw.get("execution") or {}
        return {"status": "observed" if result.get("state_after") else "unknown",
                "state_reads": result.get("state_after", []),
                "reason": "Anvil property checks require configured ABI calls in the existing spec"}

    def to_v2_feedback(self, raw: dict[str, Any]) -> dict[str, Any]:
        result = raw.get("execution") or {}
        txs = result.get("transactions", [])
        return {"backend": self.name, "deployment": result.get("deployment", {}),
                "transactions": [normalize_transaction(row) for row in txs],
                "sequence_success": bool(txs) and all(row.get("status") == 1 for row in txs),
                "property_checks_passed": None,
                "state_before": result.get("state_before", []),
                "state_after": result.get("state_after", []),
                "capabilities": {"msg_sender": True, "internal_prank": False,
                                 "internal_warp": False, "mined_transaction_receipts": True,
                                 "revert_data": False, "state_observation": bool(result.get("state_after")),
                                 "rpc_impersonation_used": False},
                "status": result.get("status", raw.get("status")),
                "limitation": "Ordinary RPC sender selection does not implement HEVM calls from inside the Harness."}


def normalize_transaction(row: dict[str, Any]) -> dict[str, Any]:
    success = row.get("status") in (1, "success", "passed")
    revert = row.get("return_data") or row.get("trace", {}).get("return_value")
    return {"transaction_index": row.get("index"), "function": row.get("function"),
            "arguments": row.get("arguments", []), "sender": row.get("sender"),
            "value_wei": str(row.get("value_wei", row.get("value", "0"))),
            "status": "success" if success else "reverted", "revert_data": revert,
            "revert_reason": decode_revert(revert), "gas_used": row.get("gas_used"),
            "gas_used_estimate": row.get("gas_used_estimate"), "block_number": row.get("block_number"),
            "origin": row.get("origin"),
            "timestamp_before": row.get("timestamp_before"), "timestamp_at_call": row.get("timestamp_at_call"),
            "timestamp_after": row.get("timestamp_after"),
            "observations_before": row.get("observations_before", []),
            "observations_after": row.get("observations_after", []),
            "property_checks": row.get("property_checks", []),
            "target_property": row.get("target_property")}


def decode_observation(data: str, output_type: Optional[str]) -> Any:
    """Decode common scalar ABI getter results while retaining the raw bytes."""
    if not isinstance(data, str) or not data.startswith("0x") or not output_type:
        return data
    try:
        raw = bytes.fromhex(data[2:])
    except ValueError:
        return data
    if output_type.startswith(("uint", "int")) and len(raw) >= 32:
        bits = int(re.sub(r"\D", "", output_type) or "256")
        value = int.from_bytes(raw[-32:], "big")
        if output_type.startswith("int") and value >= 1 << (bits - 1):
            value -= 1 << bits
        return str(value)
    if output_type == "bool" and len(raw) >= 32:
        return bool(int.from_bytes(raw[-32:], "big"))
    if output_type == "address" and len(raw) >= 32:
        return "0x" + raw[-20:].hex()
    return data


def decode_revert(data: Any) -> Optional[str]:
    if not isinstance(data, str) or not data.startswith("0x"):
        return None
    raw = bytes.fromhex(data[2:])
    if len(raw) >= 68 and raw[:4].hex() == "08c379a0":
        size = int.from_bytes(raw[36:68], "big")
        return raw[68:68 + size].decode("utf-8", "replace")
    if len(raw) >= 36 and raw[:4].hex() == "4e487b71":
        return "Panic(0x%x)" % int.from_bytes(raw[4:36], "big")
    if len(raw) >= 4:
        return "CustomError(0x" + raw[:4].hex() + ")"
    return None


def fixed_echidna_corpus(sequence: dict[str, Any], target_address: str, output: Path) -> Path:
    output = output.resolve()
    corpus = output / "coverage"
    corpus.mkdir(parents=True, exist_ok=True)
    transactions = []
    for tx in sequence["transactions"]:
        signature = tx["signature"]
        args = tx.get("arguments", [])
        encoded = []
        for index, value in enumerate(args):
            abi_type = _abi_type(signature, index)
            if abi_type.startswith(("uint", "int")):
                bits = int(re.sub(r"\D", "", abi_type) or "256")
                encoded.append({"contents": [bits, str(value)], "tag": "AbiUInt" if abi_type.startswith("uint") else "AbiInt"})
            elif abi_type == "address":
                encoded.append({"contents": [str(value)], "tag": "AbiAddress"})
            elif abi_type == "bool":
                encoded.append({"contents": [bool(value)], "tag": "AbiBool"})
            else:
                raise ValueError("unsupported Echidna corpus type " + abi_type)
        transactions.append({"call": {"contents": [signature.split("(")[0], encoded], "tag": "SolCall"},
                             "delay": ["0x" + "00" * 32, "0x" + "00" * 32],
                             "dst": target_address, "gas": 12500000,
                             "gasprice": "0x" + "00" * 32, "src": tx["sender"].lower(),
                             "value": "0x" + format(int(tx.get("value_wei", 0)), "064x")})
    path = corpus / "phase40-fixed-sequence.txt"
    path.write_text(json.dumps(transactions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run_echidna_sequence(manifest: dict[str, Any], workspace: Path, sequence: dict[str, Any],
                         target_address: str, output: Path, env: dict[str, str], echidna: str) -> dict[str, Any]:
    workspace, output = workspace.resolve(), output.resolve()
    scenario_id = sequence.get("id", "sequence")
    corpus_root = output / "echidna-corpus" / scenario_id
    corpus_file = fixed_echidna_corpus(sequence, target_address, corpus_root)
    command = [echidna, str(workspace), "--contract", manifest["harness"]["contract"],
               "--config", str(workspace / manifest["harness"]["native_config"]),
               "--test-mode", manifest["harness"]["property_mode"], "--test-limit", "0",
               "--seq-len", str(len(sequence["transactions"])), "--workers", "1",
               "--seed", str(sequence.get("echidna_seed", 4040)), "--corpus-dir", str(corpus_root),
               "--format", "text", "--disable-onchain-sources", "--contract-addr", target_address]
    if manifest.get("deployment", {}).get("deployer"):
        command.extend(["--deployer", manifest["deployment"]["deployer"]])
    for account in manifest.get("accounts", []):
        command.extend(["--sender", account["address"]])
    log = output / (scenario_id + ".echidna-native.log")
    try:
        completed = _run(command, workspace, env, timeout=int(sequence.get("timeout", 300)), log_path=log)
        text = completed.stdout
        properties = re.findall(r"^([^\n:]+): (passing|failing|failed)$", text, re.MULTILINE)
        loaded = [int(value) for value in re.findall(r"Loaded\s+(\d+)\s+transaction sequences", text)]
        replayed = "Sequence replayed from corpus file" in text
        failed = bool(re.search(r"\b(?:falsified|failed)\b", text, re.IGNORECASE))
        raw = {"backend": "echidna-native", "command": command, "returncode": completed.returncode,
               "corpus_file": str(corpus_file), "corpus_sha256": sha256_file(corpus_file),
               "log": str(log), "log_sha256": sha256_file(log),
               "loaded_sequences": max(loaded, default=0), "seed_replay_observed": replayed,
               "property_failure_observed": failed,
               "properties": [{"name": name.strip(), "status": status} for name, status in properties],
               "status": "passed" if completed.returncode == 0 and replayed and not failed else "execution_failed"}
    except Exception as exc:
        raw = {"backend": "echidna-native", "command": command, "log": str(log),
               "status": "execution_failed", "error": "%s: %s" % (type(exc).__name__, exc)}
    write_json(output / (scenario_id + ".echidna-native.json"), raw)
    return raw


def execution_request(sequence: dict[str, Any]) -> ExecutionRequest:
    txs = [Transaction(item["signature"], item.get("arguments", []), item["sender"],
                       str(item.get("value_wei", "0")), item.get("timestamp"),
                       int(item.get("delay_seconds", 0)), item.get("block_number"), item.get("origin"))
           for item in sequence["transactions"]]
    return ExecutionRequest(sequence["id"], txs, bool(sequence.get("continue_after_failure", False)))
