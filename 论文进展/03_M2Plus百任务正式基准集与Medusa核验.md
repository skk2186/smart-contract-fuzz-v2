# M2-Plus 进展记录：100 任务正式论文基准集定型与 Medusa 1.5.1 核验

> 完成日期：2026-11-28  
> 选定路线：**路线 A（100 个正式安全属性任务 + Echidna 2.3.2 / Medusa 1.5.1 双 SOTA 引擎对比）**  
> 正式冻结清单：`func/测试过程/SCFuzzBench公开项目接入/结果/M2Plus大规模基准集/dataset_manifest_100.json`  
> 自动化接入脚本：`func/测试过程/M2Plus外部基准接入与摸底.py`、`func/测试过程/M2Plus补齐至100任务.py`

---

## 一、100 任务正式论文基准集构成（94% 纯外部真实开源/主网合约）

本基准集共涵盖 **48 个独立智能合约与真实大型多合约协议**、精确 **100 条安全属性任务**，全部通过统一硬准入门（固定 `solc` 零魔改编译、Slither 属性分析通过、Anvil 部署后初始属性均为 `True`、Echidna 2.3.2 正常执行）：

| 基准分组 | 合约 / 协议数 | 属性任务数 | 来源说明 | Native Echidna 摸底（20,000 次 / 30s） | 论文核心角色 |
|---|---:|---:|---|---|---|
| **Benchmark A1**<br>纯外部公开/主网真实漏洞 | **42 个合约** | **42** | 34 个官方 **SmartBugs Curated**（commit `230e649123...`，零修改上游原文）、3 个 **Trail of Bits** `building-secure-contracts`（官方自带原生 `echidna_*`）、3 个 **OpenZeppelin Ethernaut**、2 个 **Capture The Ether** | **15/42（35.7%）** 命中，**27/42（64.3%）** 未命中 | **RQ1 主表**：反例发现率与首次发现时间（TTFB），兼具自然难度梯度 |
| **Benchmark B**<br>真实大型开源多合约协议 | **6 大开源协议** | **52** | 全部复用仓库已归档真实项目：`Immutable` (22)、`Request` (16)、`Hokusai` (5)、`BeeStorage` (4)、`Kink` (3)、`OpenNFTs` (2) | 52/52 初始属性均为 `True` 且具合法候选动作 | **RQ2 主表**：真实大规模多合约有效种子率、seed-only 深度覆盖与冷启动加速 |
| **Benchmark A2**<br>受控 DeFi 深层状态机与动态 ID | **6 个合约** | **6** | 面向 ERC-4626 首存通胀、治理双花、AMM 预言机操纵、动态 `bytes32` 事件 ID 托管/拍卖与多签绕过 | **0/6（0%）** 命中 | **RQ3 受控消融集**：拆解 Layer 1 动态 `bytes32` 事件绑定、Stage 1 与 Stage 2 独立贡献 |
| **总计** | **54 个合约/协议（48 个外部真实）** | **100** | **94% 纯外部真实开源/主网合约** | **100/100 全部准入** | **全面支撑 CCF-C 论文 RQ1–RQ4** |

> 排除说明：`Phase32PigfoxRWADemo` 原生配置走 `run_echidna` 受 Foundry `foundry-pp` 限制退出（`rc=1`），`Kink.echidna_reserves_match_balances` 初始状态即为 `False`，`SmartBugs/lottery.sol` 为 0.4.0 非 payable 语法——均按客观准入门剔除并如实记录。

---

## 二、本轮核心静态分析升级：3 跳守卫 / Modifier / ETH 平衡写者闭包

在 `func/功能/属性种子上下文.py` 完善了通用的 **3 跳前置依赖写者闭包**：
1. **ETH 余额隐式写者闭包**：当目标属性或候选动作读取 `.balance` 时，自动补齐 `payable` 与 ETH 转账函数；
2. **Slither 守卫与 helper 写者闭包**：沿 `guards[].state_reads` 及直接调用的 helper 补齐写者；
3. **源码级 Modifier / 守卫赋值写者闭包**：解决 Slither `effect_catalog` 仅索引属性直写函数、漏掉 `modifier onlyOwner` 涉及的 `initWallet()` / `newOwner()` / `IamMissing()` 等关键前置权限写者的普遍局限。

---

## 三、Medusa 1.5.1 双引擎基线链路核验

- 本地二进制：`.tools/medusa/linux/medusa`（`medusa version 1.5.1`）
- 实测验证：在 `EthernautDex` 上 3 秒完成 `20,870` 次调用（`546` branches，`corpus=15`，自动生成 LCOV 与 HTML 覆盖报告），原生 Medusa 同样 `[PASSED]`（未发现反例）。
- 结论：**Medusa 1.5.1 可直接作为 RQ4 的第二工业级 SOTA 基线与跨引擎种子赋能验证目标。**

---

## 四、下一步：正式启动 M3（冻结版本全量 100 任务实验）

M3 严格按 4 个清晰批次执行，**每完成一批自动更新 `论文进展/` 并推送 GitHub**：
- **M3-Batch 1**：Benchmark A1（42 个外部真实漏洞）+ Benchmark A2（6 个受控 DeFi 消融）= **48 个反例靶 × 4 臂完整消融（`native` / `oneshot` / `stage1_only` / `hybrid`）× 3 随机种子**（产出论文 **RQ1 + RQ3** 主大表）。
- **M3-Batch 2**：Benchmark B（6 大真实开源多合约协议全部 **52 条原生属性** × 3 臂对照，产出论文 **RQ2** 主大表）。
- **M3-Batch 3**：**Medusa 1.5.1 双引擎对比与种子赋能实验**（在代表性反例靶与真实协议上跑 `Native Medusa` vs `Seeded Medusa`，产出 **RQ4**）。
- **M3-Batch 4**：全量数据统计检验（Mann-Whitney U / Fisher 精确检验）、Token/时间开销汇总与论文高清图表一键生成。
