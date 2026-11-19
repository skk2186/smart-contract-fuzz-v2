#!/usr/bin/env python3
"""从当前分支的父提交恢复 Phase30A 正文并追加恢复执行记录。"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[6]
DOC = ROOT / "docs/30_轻量级公开合约接入试点.md"
HISTORICAL = "HEAD^:docs/30_轻量级公开合约接入试点.md"
APPENDIX = r"""

## Phase30A 恢复执行记录

记录日期：2026-11-19；执行基线：`96ade661d7ffef5b80b040a0f069afe38533dbd4`

本节追加于原始冻结报告之后，保留其“执行在原生编译前受环境阻塞”的历史判断。恢复运行是在后续阶段解决 WSL 工具可用性之后进行，不回写为原阶段已经具备的证据。

### 恢复后实际执行

- 使用原冻结的 Solidity 0.4.24、Wallet 原始业务逻辑和五账户 Harness 完成编译；Slither 输出记录在 `func/测试过程/SCFuzzBench公开项目接入/结果/Wallet02Refund/05-Harness编译.json` 与 `04-slither-property-analysis.json`。
- Agent A 只生成 `deposit(uint8) → refund(uint8)` 两笔序列。Agent B 保留函数顺序；第一次参数化的存款为 1 ETH，因统一初始余额仅 4294967295 wei 而在 Anvil 报 `Insufficient funds`。一次反馈参数修复将金额改为 0.001 ETH，仍没有增添交易步骤。
- 按环境修订将 Anvil 与 Echidna 统一初始余额提高到 100 ETH 后，原始和反馈修复候选均能完整执行。两者被选账户的累计提款均等于累计存款，冻结目标仍为假；没有达到目标状态。逐笔记录见 `06b-funded-replay/anvil-replay.json` 与 `target-state-getters.json`。
- Echidna 从两个分离语料各加载并回放 1 条两笔序列，属性均通过。日志 `tests: 0/1, fuzzing: 3/1`，输出覆盖序列与输入语料在交易语义上相同，没有后续模糊测试新序列或新增覆盖。原始汇总里的 `mutation_evidence: true` 是对 `fuzzing` 计数的过度解释，不能作为变异证据；原记录及其更正解释保存在 `06b-funded-replay/echidna-seed-replay.json`。

### 恢复阶段结论

恢复执行证明 Phase30A 冻结输入可以编译、产生候选并由 Anvil/Echidna 回放；它没有证明目标可达，也没有产生目标反例。目标是否可达及序列规划缺陷留待 Phase30B 通过独立人工诊断和后续受控修复验证。原冻结属性、许可和时间线均未改写；100 ETH 是基于 RPC 余额错误记录的环境修订，不是算法或属性变更。
"""


def main() -> None:
    historical = subprocess.run(["/usr/bin/git", "show", HISTORICAL], cwd=ROOT,
                                 check=True, capture_output=True).stdout.decode("utf-8")
    current = DOC.read_text(encoding="utf-8")
    if "## Phase30A 恢复执行记录" in current:
        raise FileExistsError("文档已含恢复记录，拒绝覆盖")
    if len(current.splitlines()) > 5:
        raise RuntimeError("当前文档并非意外缩短版本，停止覆盖以保护已有内容")
    DOC.write_text((historical.rstrip() + APPENDIX).rstrip() + "\n", encoding="utf-8")
    print(f"restored={DOC.relative_to(ROOT)} historical_bytes={len(historical.encode('utf-8'))}")


if __name__ == "__main__":
    main()
