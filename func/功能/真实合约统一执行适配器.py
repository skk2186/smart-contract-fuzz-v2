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
    # In isolated worktrees ROOT may be nested under .tools, so sibling
    # executables must be resolved from the configured forge binary.
    tool_home = Path(tools["forge"]).resolve().parents[2]
    env["PATH"] = os.pathsep.join([str(Path(tools["forge"]).resolve().parent),
                                   str(tool_home / "olympia-venv/bin"), env.get("PATH", "")])
    env["PYTHONPATH"] = os.pathsep.join([str(tool_home / "python"), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
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
        " function _writeObservation(string memory path,uint256 index,string memory phase,string memory name,address receiver,bytes memory input) internal {",
        "  (bool ok,bytes memory data)=receiver.staticcall(input);",
        "  vm.writeLine(path,string.concat(\"OBS\\t\",_uint(index),\"\\t\",phase,\"\\t\",name,\"\\t\",ok?\"success\":\"error\",\"\\t0x\",_hex(data),\"\\t\",_address(receiver)));",
        " }",
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
        source.append("  _writeObservation(path,index,phase,%s,%s,%s);" %
                      (_sol_string(observer["name"]), target_expr, encoded))
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
    # Capture the deployed state before the first candidate call. This is an
    # observation only; do not invoke potentially stateful Assertion Harness
    # methods here.
    source.append("  _observe(target,path,0,\"initial\");")
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
    lines = [
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
    ]
    execution = manifest.get("execution", {})
    # Match the deterministic runtime presented to Agent B and the native
    # runner. Foundry's default (timestamp/block 1) silently diverges from the
    # project's declared environment.
    if execution.get("deployment_timestamp") is not None:
        lines.insert(-1, "block_timestamp = %d" % int(execution["deployment_timestamp"]))
    if execution.get("deployment_block_number") is not None:
        lines.insert(-1, "block_number = %d" % int(execution["deployment_block_number"]))
    if execution.get("chain_id") is not None:
        lines.insert(-1, "chain_id = %d" % int(execution["chain_id"]))
    if execution.get("gas_price") is not None:
        lines.insert(-1, "gas_price = %d" % int(execution["gas_price"]))
    return "\n".join(lines)


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

    def to_v2_feedback(self, raw: dict[str, Any], *, target_property_signature: str | None = None,
                       predicate_observers: list[str] | None = None) -> dict[str, Any]:
        return execution_feedback_to_v2(
            raw, self.manifest, backend=self.name,
            target_property_signature=target_property_signature,
            predicate_observers=predicate_observers)


def _parse_tsv(path: Path, request: ExecutionRequest, manifest: dict[str, Any]) -> dict[str, Any]:
    deployment = {}
    tx_map: dict[int, dict[str, Any]] = {}
    properties = []
    initial_observations = []
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
                           "output_type": definition.get("output_type"),
                           "receiver": definition.get("receiver") or
                                       ("harness" if definition.get("target") == "harness" else name),
                           "receiver_address": fields[6] if len(fields) > 6 else None,
                           "source": {"backend": "foundry-cheatcode", "phase": phase,
                                      "transaction_index": idx}}
            if observation["success"]:
                observation["value"] = decode_observation(raw, definition.get("output_type"))
            if phase == "initial" or idx == 0:
                initial_observations.append(observation)
            else:
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
            "deployment": deployment, "initial_observations": initial_observations,
            "transactions": txs, "properties": properties,
            "capabilities": {"internal_prank": True, "internal_warp": True,
                             "per_call_status": True, "mined_receipts": False,
                             "state_observation": True}}


class AnvilRpcBackend(ExecutionBackend):
    """包装 Phase39 的原 Anvil 执行器；不声称支持内部 HEVM cheatcode。"""
    name = "anvil-rpc"

    def __init__(self, python: str, output: Path, env: dict[str, str],
                 spec_template: Optional[Path] = None,
                 manifest: Optional[dict[str, Any]] = None):
        self.python, self.output, self.env = python, output.resolve(), env
        self.spec_template = spec_template.resolve() if spec_template else None
        self.manifest = manifest or {}
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

    def to_v2_feedback(self, raw: dict[str, Any], *, target_property_signature: str | None = None,
                       predicate_observers: list[str] | None = None) -> dict[str, Any]:
        return execution_feedback_to_v2(
            raw, self.manifest, backend=self.name,
            target_property_signature=target_property_signature,
            predicate_observers=predicate_observers)


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


def _v2_observation(item: dict[str, Any], backend: str) -> dict[str, Any]:
    raw_status = item.get("status")
    is_observed = ((item.get("success") is True and "value" in item) or
                   raw_status == "observed" or
                   (raw_status in (1, "success", "passed") and "value" in item))
    signature = item.get("signature") or item.get("function")
    name = item.get("name") or item.get("label") or signature
    value = item.get("value") if is_observed else None
    if is_observed and item.get("output_type") == "bool" and isinstance(value, str):
        if value.lower() in {"true", "1"}:
            value = True
        elif value.lower() in {"false", "0"}:
            value = False
    return {"name": name,
            "signature": signature,
            "receiver": item.get("receiver", name),
            "receiver_address": item.get("receiver_address"),
            "arguments": item.get("arguments", []),
            "output_type": item.get("output_type"),
            "value": value,
            "raw": item.get("raw"),
            # Backward-compatible alias for existing V2 consumers that still
            # read success; status remains the canonical observation field.
            "success": is_observed,
            "status": "observed" if is_observed else "call_error",
            "source": item.get("source") or {"backend": backend, "kind": "configured_getter_call"}}


def _getter_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return (str(item.get("signature")), str(item.get("receiver")),
            json.dumps(item.get("receiver_address"), sort_keys=True),
            json.dumps(item.get("arguments", []), sort_keys=True))


def _target_result(row: dict[str, Any], signature: str | None) -> tuple[Any, str, dict[str, Any] | None]:
    if not signature:
        return None, "unknown", None
    checks = [item for item in row.get("property_checks", [])
              if str(item.get("signature", "")).rsplit(".", 1)[-1] ==
              str(signature).rsplit(".", 1)[-1]]
    if checks:
        check = checks[-1]
        value = bool(check.get("success"))
        return value, "passed" if value else "failed", {
            "source": "backend_property_check", "signature": signature,
            "return_data": check.get("return_data") or check.get("revert_data")}
    if str(row.get("function", "")).rsplit(".", 1)[-1] != str(signature).rsplit(".", 1)[-1]:
        return None, "not_checked", None
    success = row.get("status") in (1, "success", "passed")
    data = row.get("return_data") or row.get("revert_data")
    try:
        reason = decode_revert(data)
    except (TypeError, ValueError):
        reason = None
    if success:
        return True, "passed", {"source": "assertion_transaction_success",
                                "signature": signature, "return_data": data}
    # A revert is a property counterexample only when the Solidity assertion
    # panic selector and code are known. Other reverts can be precondition errors.
    if reason == "Panic(0x1)":
        return False, "failed", {"source": "assertion_panic_revert",
                                 "signature": signature, "return_data": data,
                                 "revert_reason": reason}
    return None, "unknown", {"source": "transaction_revert_not_attributable_to_assertion",
                             "signature": signature, "return_data": data,
                             "revert_reason": reason}


def execution_feedback_to_v2(raw: dict[str, Any], manifest: dict[str, Any], *,
                             backend: str | None = None,
                             target_property_signature: str | None = None,
                             predicate_observers: list[str] | None = None) -> dict[str, Any]:
    """Map backend evidence to the V2 replay/E2/E3 shape without inferring state.

    Only explicit predicate observer bindings enter predicate_getter_values.
    Other getter observations stay available as general state feedback. If a
    property operand is not externally observable, its value remains unknown.
    """
    execution = raw.get("execution") or raw
    backend_name = backend or raw.get("backend") or execution.get("backend", "unknown")
    target_property_signature_source = "explicit" if target_property_signature else "unknown"
    if not target_property_signature:
        declared = list(manifest.get("native_assertions", []))
        declared.extend(manifest.get("property_observation", {}).keys())
        declared.extend(item.get("signature") for item in manifest.get("properties", [])
                        if item.get("kind") in {"assertion", "assertion_test"})
        executed = {str(row.get("function")) for row in execution.get("transactions", [])}
        matches = sorted({str(signature) for signature in declared
                          if signature and str(signature) in executed})
        if len(matches) == 1:
            target_property_signature = matches[0]
            target_property_signature_source = "manifest_declared_assertion_invoked_by_sequence"
    definitions = manifest.get("observers", [])
    property_observation = (manifest.get("property_observation", {})
                            .get(target_property_signature, {}))
    selected = set(predicate_observers or
                   property_observation.get("predicate_observers") or
                   manifest.get("target_state_check", {}).get("getter_signatures") or
                   [str(item["name"]) for item in definitions
                    if item.get("predicate_observer") is True])
    initial_rows = execution.get("initial_observations", []) or execution.get("state_before", [])
    initial = [_v2_observation(item, backend_name) for item in initial_rows]
    sequence_after_rows = execution.get("final_observations", []) or execution.get("state_after", [])
    sequence_after = [_v2_observation(item, backend_name) for item in sequence_after_rows]
    initial_property_values: dict[str, Any] = {}
    transactions = []
    trajectory = [{"transaction_index": 0, "value": None, "status": "not_checked",
                   "predicate_getters": [item for item in initial if item.get("name") in selected],
                   "changed_predicate_getters": []}]
    prior_getters = {_getter_key(item): item["value"] for item in initial
                     if item.get("name") in selected and item.get("status") == "observed"}
    failure_evidence = []
    state_changes = []
    for row in execution.get("transactions", []):
        tx = normalize_transaction(row)
        before = [_v2_observation(item, backend_name)
                  for item in row.get("observations_before", [])]
        after = [_v2_observation(item, backend_name)
                 for item in row.get("observations_after", [])]
        before_map = {_getter_key(item): item for item in before}
        after_map = {_getter_key(item): item for item in after}
        deltas = []
        for key in sorted(set(before_map) | set(after_map), key=str):
            old, new = before_map.get(key), after_map.get(key)
            old_value = old.get("value") if old and old.get("status") == "observed" else None
            new_value = new.get("value") if new and new.get("status") == "observed" else None
            if old_value != new_value and (old is None or new is None or old or new):
                delta = {"signature": key[0], "receiver": key[1],
                         "receiver_address": json.loads(key[2]),
                         "arguments": json.loads(key[3]), "before": old_value, "after": new_value,
                         "status": ("observed" if old and new and
                                    old.get("status") == new.get("status") == "observed"
                                    else "partially_observed"),
                         "source": {"backend": backend_name, "kind": "before_after_getter_diff"}}
                deltas.append(delta)
                state_changes.append(delta)
        predicate_values = [item for item in after if item.get("name") in selected]
        changed_predicates = []
        for getter in predicate_values:
            if getter.get("status") != "observed":
                continue
            key = _getter_key(getter)
            if key in prior_getters and prior_getters[key] != getter.get("value"):
                changed_predicates.append({"signature": getter.get("signature"),
                                           "receiver": getter.get("receiver"),
                                           "receiver_address": getter.get("receiver_address"),
                                           "arguments": getter.get("arguments", []),
                                           "before": prior_getters[key], "after": getter.get("value"),
                                           "source": getter.get("source")})
            prior_getters[key] = getter.get("value")
        tx.update({"observations_before": before, "observations_after": after,
                   "state_getter_values": after, "predicate_getter_values": predicate_values,
                   "state_changes": deltas, "changed_predicate_getters": changed_predicates})
        value, property_status, evidence = _target_result(row, target_property_signature)
        tx["target_property"] = value
        tx["target_property_status"] = property_status
        tx["property_related_state_changed"] = (
            bool(changed_predicates) if any(item.get("status") == "observed"
                                            for item in predicate_values) else None)
        trajectory.append({"transaction_index": tx.get("transaction_index"),
                           "value": value, "status": property_status,
                           "predicate_getters": predicate_values,
                           "changed_predicate_getters": changed_predicates,
                           "property_result_evidence": evidence})
        if tx.get("status") != "success":
            evidence_row = {"transaction_index": tx.get("transaction_index"),
                            "function": tx.get("function"), "sender": tx.get("sender"),
                            "status": tx.get("status"), "revert_data": tx.get("revert_data"),
                            "revert_reason": tx.get("revert_reason"),
                            "source": {"backend": backend_name, "log": raw.get("log"),
                                       "driver_source": raw.get("driver_source")}}
            tx["failure_evidence"] = evidence_row
            failure_evidence.append(evidence_row)
        else:
            tx["failure_evidence"] = None
        transactions.append(tx)
    # Phase39's Anvil runner records getter values only at sequence boundaries.
    # The end state is exact for the final transaction, but it must not be
    # projected backwards onto earlier transactions.
    if sequence_after and transactions and not transactions[-1].get("observations_after"):
        final_tx = transactions[-1]
        final_tx["observations_after"] = sequence_after
        final_tx["state_getter_values"] = sequence_after
        final_tx["predicate_getter_values"] = [item for item in sequence_after
                                                if item.get("name") in selected or
                                                item.get("signature") in selected]
        final_tx["observation_scope"] = "after_final_transaction_only"
    initial_map = {_getter_key(item): item for item in initial}
    final_map = {_getter_key(item): item for item in sequence_after}
    sequence_state_changes = []
    for key in sorted(set(initial_map) | set(final_map), key=str):
        before_item, after_item = initial_map.get(key), final_map.get(key)
        before_value = (before_item.get("value") if before_item and
                        before_item.get("status") == "observed" else None)
        after_value = (after_item.get("value") if after_item and
                       after_item.get("status") == "observed" else None)
        if before_value == after_value:
            continue
        sequence_state_changes.append({
            "transaction_index": None,
            "signature": key[0], "receiver": key[1],
            "receiver_address": json.loads(key[2]),
            "arguments": json.loads(key[3]), "before": before_value,
            "after": after_value,
            "status": ("observed" if before_item and after_item and
                       before_item.get("status") == after_item.get("status") == "observed"
                       else "partially_observed"),
            "observation_scope": "whole_sequence_endpoints",
            "source": {"backend": backend_name,
                       "kind": "sequence_before_after_getter_diff"}})
    state_changes.extend(sequence_state_changes)
    final_property_row = next((item for item in reversed(sequence_after)
                               if str(item.get("signature", "")).rsplit(".", 1)[-1] ==
                               str(target_property_signature or "").rsplit(".", 1)[-1] and
                               item.get("status") == "observed"), None)
    final_property_value = None
    if final_property_row is not None:
        final_property_value = final_property_row.get("value")
        if isinstance(final_property_value, str):
            if final_property_value.lower() in {"true", "1"}:
                final_property_value = True
            elif final_property_value.lower() in {"false", "0"}:
                final_property_value = False
            else:
                final_property_value = None
        initial_property_row = next((item for item in initial
                                     if str(item.get("signature", "")).rsplit(".", 1)[-1] ==
                                     str(target_property_signature or "").rsplit(".", 1)[-1] and
                                     item.get("status") == "observed"), None)
        if initial_property_row is not None:
            initial_value = initial_property_row.get("value")
            if isinstance(initial_value, str):
                if initial_value.lower() in {"true", "1"}:
                    initial_value = True
                elif initial_value.lower() in {"false", "0"}:
                    initial_value = False
                else:
                    initial_value = None
            if initial_value is not None:
                initial_property_values = {target_property_signature: initial_value}
        if transactions and final_property_value is not None:
            transactions[-1]["target_property"] = final_property_value
            transactions[-1]["target_property_status"] = (
                "passed" if final_property_value else "failed")
            transactions[-1]["property_observation_scope"] = "after_final_transaction"
    else:
        initial_property_values = {}
    sequence_predicate_changes = [item for item in sequence_state_changes
                                  if item.get("signature") in selected or
                                  item.get("receiver") in selected]
    if sequence_after and (target_property_signature or selected):
        trajectory.append({
            "transaction_index": len(transactions),
            "value": final_property_value,
            "status": "passed" if final_property_value is True else
                      "failed" if final_property_value is False else
                      "unknown" if target_property_signature else "not_checked",
            "observation_scope": "after_sequence",
            "predicate_getters": [item for item in sequence_after
                                  if item.get("name") in selected or
                                  item.get("signature") in selected],
            "changed_predicate_getters": sequence_predicate_changes,
            "property_result_evidence": {
                "source": "configured_property_getter_after_sequence",
                "signature": target_property_signature,
                "value": final_property_value,
                "transaction_level_observation": "unknown"}})
    observed_predicates = [item for entry in trajectory
                           for item in entry["predicate_getters"]
                           if item.get("status") == "observed"]
    failed_predicates = [item for entry in trajectory
                         for item in entry["predicate_getters"]
                         if item.get("status") != "observed"]
    changed = any(entry["changed_predicate_getters"] for entry in trajectory)
    counterexample = any(entry.get("value") is False for entry in trajectory)
    property_check_passed = any(entry.get("value") is True and
                                entry.get("status") == "passed" for entry in trajectory)
    if counterexample:
        target_status = "counterexample_state_established"
    elif final_property_value is True:
        target_status = "property_holds_after_sequence"
    elif property_check_passed:
        target_status = "property_check_passed"
    elif changed:
        target_status = "property_related_state_changed_property_holds"
    elif target_property_signature and (failed_predicates or not observed_predicates):
        target_status = "property_state_unobservable"
    else:
        target_status = "no_observed_property_related_state_change"
    property_rows = execution.get("properties", [])
    target_checks = [item for item in property_rows
                     if str(item.get("signature", "")).rsplit(".", 1)[-1] ==
                     str(target_property_signature or "").rsplit(".", 1)[-1]]
    foundry = backend_name == "foundry-cheatcode"
    capabilities = ({"msg_sender": True, "tx_origin": True, "internal_prank": True,
                     "internal_warp": True, "internal_roll": True,
                     "per_call_success_or_failure": True, "revert_data": True,
                     "state_observation": bool(initial or transactions),
                     "sequence_endpoint_state_observation": bool(sequence_after),
                     "per_transaction_state_observation": bool(transactions) and all(
                         row.get("observations_after") for row in transactions),
                     "mined_transaction_receipts": False, "transaction_boundaries": False,
                     "gas_used_is_estimate": True, "rpc_impersonation_used": False}
                    if foundry else
                    {"msg_sender": True, "tx_origin": False, "internal_prank": False,
                     "internal_warp": False, "per_call_success_or_failure": True,
                     "revert_data": False, "state_observation": bool(initial or transactions),
                     "sequence_endpoint_state_observation": bool(sequence_after),
                     "per_transaction_state_observation": bool(transactions) and all(
                         row.get("observations_after") for row in transactions),
                     "mined_transaction_receipts": True, "rpc_impersonation_used": False})
    deployment_raw = execution.get("deployment", {})
    deployment = dict(deployment_raw)
    if "success" not in deployment:
        deployment["success"] = (deployment_raw.get("status") in
                                 (1, "success", "passed", "deployed"))
    if "target_address" not in deployment and deployment_raw.get("contract_address"):
        deployment["target_address"] = deployment_raw.get("contract_address")
    if "transaction_hash" not in deployment and deployment_raw.get("tx_hash"):
        deployment["transaction_hash"] = deployment_raw.get("tx_hash")
    all_succeeded = bool(transactions) and all(row.get("status") == "success" for row in transactions)
    backend_properties_passed = (all(item.get("success") is True for item in property_rows)
                                 if property_rows else None)
    target_entries = [entry for entry in trajectory
                      if entry.get("status") in {"passed", "failed", "unknown"}]
    target_value = target_entries[-1].get("value") if target_entries else None
    if (execution.get("status", raw.get("status")) not in {"execution_failed", "unsupported_semantics"}
            and backend_properties_passed is not False and deployment.get("success") and all_succeeded and (
            not target_property_signature or target_value is True)):
        replay_status = "executable"
    elif target_property_signature and not target_entries:
        replay_status = "target_property_not_reached"
    elif target_property_signature and target_value is None:
        replay_status = "target_property_unknown"
    else:
        replay_status = "replay_failed"
    return {"feedback_schema_version": 2, "backend": backend_name,
            "deployment": deployment, "deployment_status": "success" if deployment.get("success") else "failed",
            "replay_status": replay_status,
            "transactions": transactions, "properties": property_rows,
            "resolved_transactions": [{key: row.get(key) for key in (
                "function", "arguments", "sender", "origin", "value_wei",
                "timestamp_at_call", "timestamp_after", "status")}
                for row in transactions],
            "state_changes": state_changes, "state_before": initial,
            "state_after": sequence_after or (transactions[-1].get("observations_after", [])
                                               if transactions else initial),
            "initial_predicate_getters": [item for item in initial if item.get("name") in selected],
            "initial_property_values": initial_property_values, "initial_property_errors": {},
            "target_property_state": {
                "property": target_property_signature, "status": target_status,
                "semantics": "Only explicit predicate getter bindings and exact assertion outcomes are used; unavailable operands remain unknown.",
                "predicate_observation_completeness": (
                    "complete" if final_property_value is not None else
                    property_observation.get("completeness", "unknown" if selected else "unobservable")),
                "unobservable_predicate_operands": property_observation.get(
                    "unobservable_operands", []),
                "target_property_state_established": bool(changed or counterexample),
                "counterexample_state_established": counterexample,
                "property_related_state_changed": bool(changed) if observed_predicates else None,
                "first_established_transaction_index": next(
                    (entry.get("transaction_index") for entry in trajectory
                     if entry.get("value") is False),
                    next((entry.get("transaction_index") for entry in trajectory
                          if entry.get("changed_predicate_getters")), None)),
                "first_property_related_change_transaction_index": next(
                    (entry.get("transaction_index") for entry in trajectory
                     if entry.get("changed_predicate_getters")), None),
                "first_counterexample_transaction_index": next(
                    (entry.get("transaction_index") for entry in trajectory
                     if entry.get("value") is False), None),
                "trajectory": trajectory},
            "sequence_success": bool(transactions) and
                                all(row.get("status") == "success" for row in transactions),
            "backend_property_checks_passed": backend_properties_passed,
            "target_property_signature_source": target_property_signature_source,
            "property_checks_passed": (
                all(item.get("success") is True for item in target_checks)
                if target_checks else
                target_value if target_property_signature else
                all(item.get("success") is True for item in property_rows)
                if property_rows else None),
            "target_property_violation": next((
                {"transaction_index": entry.get("transaction_index"),
                 "property": target_property_signature}
                for entry in trajectory if entry.get("value") is False), None),
            "failure_evidence": failure_evidence,
            "unknown_fields": (
                ([{"field": "target_property_state.predicate_getter_values",
                   "status": "unknown",
                   "reason": (property_observation.get("unknown_reason") or
                              "no explicit predicate observer binding was configured or the backend did not observe one"),
                   "unobservable_operands": property_observation.get(
                       "unobservable_operands", [])}]
                 if (not observed_predicates or
                     (final_property_value is None and
                      property_observation.get("completeness") not in {None, "complete"}))
                 else []) +
                ([{"field": "transactions.per_transaction_state_observations",
                   "status": "unknown",
                   "reason": "backend returned sequence endpoint getters only; intermediate transaction state was not observed"}]
                 if transactions and not all(row.get("observations_after") for row in transactions)
                 else [])),
            "capabilities": capabilities,
            "sequence_state_changes": sequence_state_changes,
            "execution_semantics": (
                "Foundry calls share one test transaction; vm.prank/vm.warp are native cheatcodes. Per-call status is observed, but independent mined receipts do not exist."
                if foundry else
                "Anvil calls are independent RPC transactions; this backend does not implement internal Harness prank/warp semantics."),
            "status": execution.get("status", raw.get("status"))}


def fixed_echidna_corpus(sequence: dict[str, Any], target_address: str, output: Path) -> Path:
    output = output.resolve()
    corpus = output / "coverage"
    corpus.mkdir(parents=True, exist_ok=True)
    transactions = []
    for tx in sequence["transactions"]:
        signature = tx.get("signature") or tx.get("abi_signature") or tx.get("function")
        if not signature:
            raise ValueError("transaction is missing an ABI signature")
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
        # Match property outcome tokens, not words inside property names such as
        # `failed()` or `assertionFailed()`, which Echidna reports as passing.
        failed = bool(re.search(r"\bfalsified\b", text, re.IGNORECASE)
                      or re.search(r"^[^\n:]+: (?:failing|failed)$", text, re.MULTILINE))
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
