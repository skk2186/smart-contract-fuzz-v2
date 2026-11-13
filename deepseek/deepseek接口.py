#!/usr/bin/env python3
"""DeepSeek JSON 调用、Token/费用估算和逐次错误记录。"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import requests


ROOT = Path(__file__).resolve().parents[1]
KEY_FILE = ROOT / ".tools/deepseek.key"
DEFAULT_LOG = ROOT / "deepseek/结果/DeepSeek调用记录.jsonl"
PRICING_URL = "https://api-docs.deepseek.com/quick_start/pricing/"
PRICING_DATE = "2026-11-13"
RATES_USD_PER_M = {
    "offpeak": {"cache_hit": Decimal("0.003"), "cache_miss": Decimal("0.15"),
                "output": Decimal("0.6")},
    "peak": {"cache_hit": Decimal("0.006"), "cache_miss": Decimal("0.3"),
             "output": Decimal("1.2")},
}


class DeepSeekCallError(RuntimeError):
    def __init__(self, kind: str, message: str, status_code: int | None = None):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.status_code = status_code
        self.event: dict[str, Any] | None = None


class CallBudget:
    """单条件模型预算。UTF-8 字节数作为输入 Token 的保守上界预检。"""
    def __init__(self, max_tokens: int, deadline_monotonic: float | None = None):
        if max_tokens <= 0:
            raise ValueError("max_tokens 必须为正数")
        self.max_tokens = max_tokens
        self.deadline_monotonic = deadline_monotonic
        self.spent_tokens = 0
        self.calls = 0

    def admit(self, upper_bound: int) -> None:
        if self.deadline_monotonic is not None and time.monotonic() >= self.deadline_monotonic:
            raise DeepSeekCallError("time_budget_exceeded", "已达到本条件墙钟时间预算")
        if self.spent_tokens + upper_bound > self.max_tokens:
            raise DeepSeekCallError(
                "token_budget_exceeded",
                f"本次请求最坏上界 {upper_bound} 将超过剩余 Token 预算 "
                f"{self.max_tokens - self.spent_tokens}")

    def charge(self, upper_bound: int, event: dict[str, Any]) -> None:
        usage = event.get("usage") or {}
        measured = usage.get("total_tokens")
        amount = int(measured) if measured is not None else upper_bound
        self.spent_tokens += amount
        self.calls += 1
        event["budget"] = {"max_tokens": self.max_tokens,
                           "spent_tokens": self.spent_tokens,
                           "charged_tokens": amount,
                           "charge_source": "api_usage" if measured is not None else "request_upper_bound"}

    def remaining_seconds(self) -> int | None:
        if self.deadline_monotonic is None:
            return None
        return max(0, int(self.deadline_monotonic - time.monotonic()))


def load_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
    if not key:
        raise DeepSeekCallError("missing_key", "缺少 DEEPSEEK_API_KEY 或本地密钥文件")
    return key


def usage_and_cost(usage: dict[str, Any] | None) -> dict[str, Any] | None:
    if not usage:
        return None
    prompt = int(usage.get("prompt_tokens", 0))
    completion = int(usage.get("completion_tokens", 0))
    details = usage.get("prompt_tokens_details") or {}
    hit = int(usage.get("prompt_cache_hit_tokens",
                        details.get("cached_tokens", 0)))
    miss = int(usage.get("prompt_cache_miss_tokens", prompt - hit))
    if min(prompt, completion, hit, miss) < 0 or hit + miss != prompt:
        raise DeepSeekCallError("invalid_usage", "API Token 统计不一致")
    costs = {}
    for period, rates in RATES_USD_PER_M.items():
        amount = (Decimal(hit) * rates["cache_hit"] +
                  Decimal(miss) * rates["cache_miss"] +
                  Decimal(completion) * rates["output"]) / Decimal(1_000_000)
        costs[period] = str(amount)
    return {"prompt_tokens": prompt, "prompt_cache_hit_tokens": hit,
            "prompt_cache_miss_tokens": miss, "completion_tokens": completion,
            "total_tokens": prompt + completion,
            "estimated_cost_usd": costs,
            "pricing_date": PRICING_DATE, "pricing_source": PRICING_URL,
            "cost_is_estimate": True}


def _append_log(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def call_json(*, system: str, user: str, tag: str, model: str = "deepseek-flash",
              max_tokens: int = 2048, thinking: str = "disabled",
              validator: Callable[[dict[str, Any]], None] | None = None,
              log_path: Path = DEFAULT_LOG, timeout: int = 120,
              max_retries: int = 1,
              budget: CallBudget | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """返回已校验 JSON 与本次成功用量；所有尝试都写日志，不记录密钥/请求正文。"""
    if "json" not in (system + user).lower():
        raise ValueError("JSON 模式提示必须明确包含 JSON")
    key = load_key()
    payload = {"model": model,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}],
               "response_format": {"type": "json_object"},
               "thinking": {"type": thinking},
               "max_tokens": max_tokens,
               "temperature": 0,
               "stream": False}
    request_hash = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    request_upper_bound = len(system.encode("utf-8")) + len(user.encode("utf-8")) + max_tokens
    for attempt in range(max_retries + 1):
        started = time.monotonic()
        event: dict[str, Any] = {"at_utc": datetime.now(timezone.utc).isoformat(),
                                  "tag": tag, "model_requested": model,
                                  "thinking": thinking, "request_sha256": request_hash,
                                  "attempt": attempt + 1, "max_tokens": max_tokens}
        if budget:
            try:
                budget.admit(request_upper_bound)
                remaining = budget.remaining_seconds()
                if remaining == 0:
                    raise DeepSeekCallError("time_budget_exceeded", "已达到本条件墙钟时间预算")
                event["budget_preflight_upper_bound"] = request_upper_bound
                event["budget_remaining_before_call"] = budget.max_tokens - budget.spent_tokens
            except DeepSeekCallError as error:
                event.update({"ok": False, "error_kind": error.kind, "error": str(error),
                              "elapsed_seconds": 0})
                _append_log(log_path, event)
                error.event = event
                raise
        try:
            response = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                json=payload,
                timeout=min(timeout, remaining) if budget and remaining is not None else timeout)
            event["http_status"] = response.status_code
            if response.status_code != 200:
                try:
                    error = response.json().get("error", {})
                    message = str(error.get("message", response.reason))
                except (ValueError, AttributeError):
                    message = response.reason
                message = message.replace(key, "[REDACTED]")[:500]
                raise DeepSeekCallError("http_error", message, response.status_code)
            body = response.json()
            event["response_id"] = body.get("id")
            event["model_returned"] = body.get("model")
            event["system_fingerprint"] = body.get("system_fingerprint")
            event["usage"] = usage_and_cost(body.get("usage"))
            choice = body["choices"][0]
            event["finish_reason"] = choice.get("finish_reason")
            if event["finish_reason"] != "stop":
                raise DeepSeekCallError("incomplete_response", str(event["finish_reason"]))
            content = choice["message"].get("content")
            if not content or not content.strip():
                raise DeepSeekCallError("empty_json", "JSON 模式返回空内容")
            try:
                data = json.loads(content)
            except json.JSONDecodeError as exc:
                raise DeepSeekCallError("invalid_json", str(exc)) from exc
            if not isinstance(data, dict):
                raise DeepSeekCallError("invalid_shape", "顶层必须是 JSON 对象")
            # 保留已解析响应，即使后续本地 Schema 校验失败，也可复现修复过程。
            event["response_json"] = data
            if validator:
                validator(data)
            event["ok"] = True
            event["elapsed_seconds"] = round(time.monotonic() - started, 3)
            if budget:
                budget.charge(request_upper_bound, event)
            _append_log(log_path, event)
            return data, event
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError,
                DeepSeekCallError) as exc:
            if isinstance(exc, DeepSeekCallError):
                error = exc
            else:
                error = DeepSeekCallError(type(exc).__name__, str(exc).replace(key, "[REDACTED]")[:500])
            event["ok"] = False
            event["error_kind"] = error.kind
            event["error"] = str(error).replace(key, "[REDACTED]")[:500]
            event["elapsed_seconds"] = round(time.monotonic() - started, 3)
            if budget:
                budget.charge(request_upper_bound, event)
            _append_log(log_path, event)
            error.event = event
            retryable = (isinstance(exc, requests.RequestException) or
                         error.kind in {"RequestException", "ConnectionError", "Timeout",
                                        "empty_json", "invalid_json", "incomplete_response"})
            retryable |= error.status_code in {429, 500, 502, 503, 504}
            if attempt >= max_retries or not retryable:
                raise error from exc
            time.sleep(min(2 ** attempt, 4))
    raise AssertionError("unreachable")
