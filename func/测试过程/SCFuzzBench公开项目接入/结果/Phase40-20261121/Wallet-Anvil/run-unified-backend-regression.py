#!/usr/bin/env python3
"""Replay the frozen Wallet sequence through the shared Anvil backend API."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[6]
RESULTS = Path(__file__).resolve().parent
OUTPUT = RESULTS / "unified-backend"
SPEC_PATH = RESULTS / "wallet-deposit-refund-spec.json"
ADAPTER_PATH = ROOT / "func/功能/真实合约统一执行适配器.py"
spec = importlib.util.spec_from_file_location("phase40_adapter", ADAPTER_PATH)
assert spec and spec.loader
adapter = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = adapter
spec.loader.exec_module(adapter)

assert adapter._abi_type("f((uint256,address),uint8)", 0) == "(uint256,address)"
assert adapter._sol_value("0x11223344", "bytes4") == 'bytes4(hex"11223344")'
try:
    adapter._sol_value([1, 2], "uint256[]")
except ValueError:
    pass
else:
    raise AssertionError("unsupported array arguments must not be encoded silently")

with tempfile.TemporaryDirectory(prefix="phase40-cache-check-") as temporary:
    base = Path(temporary)
    pinned_source = base / "pinned.txt"
    pinned_source.write_text("pinned-source\n", encoding="utf-8")
    inventory = [("nested/pinned.txt", pinned_source, adapter.sha256_file(pinned_source))]
    cache_dir = base / "cache"
    first = adapter._make_cache(cache_dir, inventory, "fixed-tree-hash", "fixed-commit", [])
    (Path(first["workspace"]) / "nested/pinned.txt").write_text("corrupted\n", encoding="utf-8")
    second = adapter._make_cache(cache_dir, inventory, "fixed-tree-hash", "fixed-commit", [])
    assert not second["workspace_reused"]
    assert (Path(second["workspace"]) / "nested/pinned.txt").read_text(encoding="utf-8") == "pinned-source\n"

sender = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
request = adapter.ExecutionRequest(
    "wallet-deposit-refund-unified",
    [
        adapter.Transaction("deposit(uint8)", [0], sender, "1000000000000000"),
        adapter.Transaction("refund(uint8)", [0], sender, "0"),
    ],
    False,
    {"anvil_spec": str(SPEC_PATH), "sender_indices": {sender.lower(): 0}},
)
backend = adapter.AnvilRpcBackend(
    str(ROOT / ".tools/olympia-venv/bin/python"), OUTPUT, os.environ.copy(), SPEC_PATH
)
raw = backend.execute_sequence(request)
feedback = backend.to_v2_feedback(raw)
properties = backend.check_properties(request, raw)
summary = {
    "backend": backend.name,
    "status": raw.get("status"),
    "deployment_success": bool((raw.get("execution") or {}).get("deployment", {}).get("status") == 1),
    "transactions_success": [row.get("status") for row in feedback.get("transactions", [])],
    "property_state": properties,
    "v2_feedback": feedback,
    "raw": raw,
}
adapter.write_json(OUTPUT / "wallet-anvil-unified-v2-feedback.json", feedback)
assert summary["status"] == "replay_completed", summary
assert summary["deployment_success"], summary
assert summary["transactions_success"] == ["success", "success"], summary
assert properties["status"] == "observed", summary
assert all(row.get("value") == "True" for row in properties["state_reads"]
           if row.get("label") in {"property_before", "property_after"}), summary
print(json.dumps({"status": summary["status"],
                  "transactions": len(summary["transactions_success"]),
                  "property_observed": properties["status"]}, ensure_ascii=False))
