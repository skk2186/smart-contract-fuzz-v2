# Phase 28：Medusa 双引擎最小可行验证

日期：2026-11-18
执行基线：`eb51e6de464ad73f1d32a2cbdd9fdeb20bc460cd`（执行前核对本地 `main` 与远端 `main` 一致）

## 结论

Medusa 1.5.1 可以读取本阶段转换出的原生 call sequence。BeeStorage 与 Immutable 的冻结种子都通过格式核验、逐笔真实回放和目标状态 getter 核验；原始种子、Harness、属性和 Solidity 源码均未修改。BeeStorage 的三轮 M1 覆盖均高于配对 M0；Immutable 的 Medusa 分支覆盖三轮均提高，LCOV 源码行数两轮提高、一轮降低，增益很小。

本阶段没有证明跨项目泛化。Immutable Harness 同时启用了 32 个 `echidna_` 属性，其中 11 个非目标属性在 M0、M1 中都报告失败；目标属性六轮均通过。一次 M1 首次运行因 Medusa 主循环 nonce 错误未生成 LCOV，隔离目录中的同配置恢复运行成功，首次失败日志仍保留。Medusa 也无法复现 Phase25 的绝对起始区块和时间戳。

**建议：B. 只实现部分兼容，保留为可选实验；Echidna 继续作为主引擎。** 两个固定案例的技术接入成立，但 Immutable 的属性噪声、一次未重现的 nonce 错误和执行上下文差异，都需要在扩大使用前解决。当前结果不能作为独立项目泛化或引擎性能领先的证据。

## 官方格式与能力核查

本阶段固定使用 Medusa `v1.5.1`，上游提交为 `540a483b7a2a35b0a6d210aeb6ae6015aa7a0f62`。版本、Linux/Windows 二进制 SHA-256、回放核验程序哈希与 Go 依赖锁定信息见[版本锁定记录](../func/测试过程/Medusa双引擎最小验证/结果/Medusa版本锁定.json)。

按该版本源码，原生语料位于 `corpusDirectory/call_sequences/*.json`；每个文件是一组有序交易，元素包含 `call`、`blockNumberDelay` 和 `blockTimestampDelay`。交易字段可携带 `from`、`to`、`nonce`、`value`、gas 参数及 ABI 编码的 `data`。Fuzzer 启动时把这些序列加入语料并执行，后续再对语料序列做变异。适配器直接写入 ABI calldata，不猜测 Medusa JSON；两个输出语料均由 `medusa corpus clean` 报告 `1 valid, 0 invalid`。该检查只在独立临时副本上运行。

`timeout` 是运行时长上限；`testLimit` 是交易调用数上限，设为 `0` 表示无上限，不代表零预算。本阶段使用 `timeout=60` 秒和 `testLimit=100000` 安全上限，六轮对照均未触发调用上限。实际调用数取 Medusa 日志中的 `calls:` 计数；覆盖同时保留 Medusa 日志的 `branches` 计数和同范围 LCOV 命中源码行数。没有把 Medusa 与 Echidna 的 unique instructions 原始值直接比较。

## 冻结输入与执行环境

输入均取自 Phase25 的既有 Anvil 有效种子，不生成新种子。

| 案例 | 种子 SHA-256 | Harness SHA-256 | ABI artifact SHA-256 | 目标状态证据 |
|---|---|---|---|---|
| BeeStorage：createBatch → topUp | `3e90b2afffba61500c9464face334bc47e78060e1aea2d58d90f72ca2b0f2211` | `ac863a20587871404c449ef6fee36496736d495bba80f639880f0c262a2b4332` | `b52571c9ec58da207d46ded4f569bcd578f09014c3431c315ffa450a03a33982` | `batchNormalisedBalance(batchId)=2`，并观察到 `BatchTopUp` 事件 |
| Immutable：mint → approve → transferFrom → safeTransferFrom | `d1aa579ef1b4da43fb14eb4b747a76f140a9690e094fd9ab9d355ce46aa1161d` | `5b96814001c3c523c768d76a48a3ce5ac429513a1b8af91e8500405ebc18d1dd` | `b9e8dbc601775b13743d60a8186893f5cc55877cf34ec5dd2c02411fce916a02` | `approve` 成功、观察到 `Approval` 事件，`getApproved(tokenId)=0x0000000000000000000000000000000000020000` |

冻结清单及逐案例机器结果：[BeeStorage 输入清单](../func/测试过程/Medusa双引擎最小验证/结果/实验/BeeStorage/frozen-inputs.json)、[BeeStorage 汇总](../func/测试过程/Medusa双引擎最小验证/结果/实验/BeeStorage/summary.json)、[BeeStorage 回放核验](../func/测试过程/Medusa双引擎最小验证/结果/实验/BeeStorage/replay-validation/seed-verification.json)；[Immutable 输入清单](../func/测试过程/Medusa双引擎最小验证/结果/实验/Immutable/frozen-inputs.json)、[Immutable 汇总](../func/测试过程/Medusa双引擎最小验证/结果/实验/Immutable/summary.json)、[Immutable 回放核验](../func/测试过程/Medusa双引擎最小验证/结果/实验/Immutable/replay-validation/seed-verification.json)。

每例的[冻结输入清单](../func/测试过程/Medusa双引擎最小验证/结果/实验/)记录了完整 Solidity 导入闭包、属性、ABI、编译参数及哈希；[部署映射](../func/测试过程/Medusa双引擎最小验证/结果/实验/)显式映射 Phase25 Harness 地址。未知目标地址会被适配器拒绝；本次 Harness 映射到 Phase25 地址，没有静默替换。

适配器保留交易顺序、函数签名和 ABI 参数、calldata、sender、value、每个 sender 的新链 nonce、相对区块/时间延迟及跨交易参数绑定清单。两例时间/区块延迟均为 0。Medusa 1.5.1 没有绝对起始 block/timestamp 配置项：Phase25 环境为 block `4,370,000`、timestamp `1,524,785,992`；Medusa 实际回放分别从 block/time `10/10`（BeeStorage）和 `6/6`（Immutable）执行。依赖绝对时间或区块的属性因此仍有环境差异。

当前适配范围是 ABI 可唯一匹配、Phase25 原始回放成功的普通函数调用。缺少 ABI 签名或参数、sender 不在部署清单、目标地址没有显式映射、calldata 与原 trace 不一致的交易会逐笔标记为 `unsupported`；转换不完整时不写入可执行语料。没有标准函数签名的合约创建/fallback 调用不在当前支持范围。

系统默认 solc 执行前后均为 `0.4.25`；实验子进程通过局部环境固定 `0.8.20+commit.a1b79de6`，未改动全局选择。Harness 的编译、转换和回放耗时分别记录在每例 `conversion-timing.json` 与 `seed-verification.json`。

## 回放阶段结果

| 案例 | 格式有效 | Medusa 接受语料 | 原交易完整回放 | 目标交易成功 | 目标状态建立 | 目标属性被识别及回放末态结果 |
|---|---|---|---|---|---|---|
| BeeStorage | 是 | 是，1/1 | 是，3/3 | 是 | 是，getter 为 2 | 已识别；`echidna_stamp_internal_pot_not_above_contract_balance()` 为 true |
| Immutable | 是 | 是，1/1 | 是，4/4 | 是 | 是，getter 与预期 spender 相同 | 已识别；`echidna_complex_transfer_sequence()` 为 true |

逐笔记录分别在 BeeStorage、Immutable 的 `replay-validation/replay-check.json` 和 `seed-verification.json`；记录包含 sender、地址、calldata、回执状态、外层回滚、内部调用错误、事件及执行 block/time。两例均无内部调用错误、无外层回滚；转换后 calldata 与 Phase25 trace 输入逐笔一致。源种子验证前后 SHA-256 一致。

## M0/M1 配对模糊测试

每组 3 轮；M0 使用空外部语料，M1 使用冻结的转换语料。固定单 worker、`callSequenceLength=8`、60 秒、100000 调用安全上限、`propertyTesting.testPrefixes=["echidna_"]`、关闭 assertion/optimization，sender、deployer、Harness 和编译设置不变。Medusa 随机种子未固定，因此表中按相同重复编号配对，仍存在随机波动。

**BeeStorage**：目标函数为 `act_actor_topUp`，目标属性每轮通过，四个 Echidna 属性均通过，未发现属性失败。

| 重复 | M0 branches | M1 branches | M1−M0 | M0 LCOV 行 | M1 LCOV 行 | M1−M0 | M0/M1 Medusa calls |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2953 | 3006 | +53 | 639 | 665 | +26 | 59031 / 58089 |
| 2 | 3176 | 3229 | +53 | 723 | 733 | +10 | 65873 / 64622 |
| 3 | 2953 | 3233 | +280 | 639 | 735 | +96 | 61715 / 53218 |

M1 的 Medusa branches 和 LCOV 行覆盖均 3/3 高于 M0。LCOV 中目标 `act_actor_topUp` 函数在 M0/M1 都有命中，因此这不是目标函数是否可达的差异。Medusa calls 随机变化且 M1 三轮低于配对 M0；调用数本身不是覆盖收益。

**Immutable**：目标函数为 `approve`。目标属性 `echidna_complex_transfer_sequence()` 在 M0/M1 六轮都通过；每轮均覆盖到 `approve`。但 `echidna_` 前缀使 Harness 中 32 个属性都被启用，Medusa 没有按单个属性排除的配置：M0、M1 每轮都是 21 项通过、11 项失败，且这些失败属性在两组均相同。失败项为 `burn`、`mint_threshold_respected`、`mint_boundary_check`、`balance_sum_property`、`balance_consistency`、`cross_group_operations`、`total_supply_sequence`、`boundary_minting_sequence`、`total_supply_matches`、`minted_tokens_have_owner`、`token_id_uniqueness`。原始失败调用序列和 trace 在每轮 `corpus/test_results/` 与 stdout 日志中；日志可见 false 返回、revert、out-of-gas、除零或算术下溢/溢出。这些非目标属性失败不能归因到 M1 种子，也没有在本阶段修改或解释 Harness 语义。

| 重复 | M0 branches | M1 branches | M1−M0 | M0 LCOV 行 | M1 LCOV 行 | M1−M0 | M0/M1 Medusa calls |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 456 | 483 | +27 | 116 | 118 | +2 | 4682 / 4603 |
| 2 | 481 | 490 | +9 | 116 | 121 | +5 | 4830 / 4657 |
| 3 | 459 | 485 | +26 | 116 | 114 | −2 | 4448 / 4142 |

M1 的 Medusa branches 三轮均高于 M0；LCOV 行数均值从 116 增至 117.7，但只有 2/3 轮提高。不能把这个小幅平均差解释成稳定收益。

Medusa 最终 LCOV 包含语料执行与变异的合并结果；本阶段没有独立 replay-only LCOV 快照，无法可靠分离“种子刚回放时的新覆盖”和“后续变异新增覆盖”。各轮原始日志、配置、LCOV 与机器摘要保存在[实验结果目录](../func/测试过程/Medusa双引擎最小验证/结果/实验/)；冗余 HTML 展示和重复编译缓存已清理，LCOV、失败测试结果及 stdout 保留。

## 异常、兼容边界与旁证

1. BeeStorage 的 M1 第一次启动曾触发 Medusa 1.5.1 `revertReporter` 对 raw calldata 的 nil `DataAbiValues.Method` 解引用。没有修改引擎代码；M0/M1 一致关闭无关的 revert reporter 后运行通过。初始错误原文保存在 `BeeStorage/runs/M1/repeat-1/medusa.stdout.revertReporter-crash.log`。
2. Immutable M1 `repeat-2` 首次运行报告 `nonce too low`（发送者交易 nonce `0`，链状态 nonce `1`），没有 LCOV。保留首次失败结果和日志；使用同一原始种子、配置和 60 秒预算在独立 `repeat-2-recovery/` 运行后成功生成覆盖。恢复运行不改种子、不调整参数。错误只观察到一次，根因尚未确证，不能视为已修复。
3. Medusa 文档说明 `excludeFunctionSignatures` 不能排除属性测试；继续使用用户要求的 `echidna_` 前缀时，Immutable 的其余属性也会参与测试。应把上述 11 项失败当作明确的测量噪声和兼容限制，而不能只看目标属性的通过结果。
4. [Phase26 报告](26_研究方案冻结与可信度核验.md)中的 Echidna 旁证显示，BeeStorage 的 seeded final LCOV 比 native 平均多 20.7 行（3/3 正向），Immutable 平均多 29 行（3/3 正向）。本阶段 Medusa 在 BeeStorage 为 +44 行且 3/3 正向；Immutable 平均 +1.7 行、2/3 正向。两例的平均方向为正，但 Immutable 的逐轮一致性和增幅弱得多。该旁证来自固定旧案例，不构成独立项目泛化，也不用于跨引擎比较原始 instruction 数。

## 复现入口与关联产物

在仓库根目录执行：

```bash
.tools/olympia-venv/bin/python "func/测试过程/Medusa双引擎最小验证.py" BeeStorage --mode prepare
.tools/olympia-venv/bin/python "func/测试过程/Medusa双引擎最小验证.py" BeeStorage --mode replay
.tools/olympia-venv/bin/python "func/测试过程/Medusa双引擎最小验证.py" BeeStorage --mode campaign --confirm-replay-evidence "func/测试过程/Medusa双引擎最小验证/结果/实验/BeeStorage/replay-validation/seed-verification.json"
.tools/olympia-venv/bin/python "func/测试过程/Medusa双引擎最小验证.py" BeeStorage --mode summary
```

Immutable 使用相同命令并把案例名改为 `Immutable`。`campaign` 有回放门槛；若需要恢复一次技术中断，`--recovery --arm M1 --repeat 2` 会使用独立目录并保留原失败产物。适配器与驱动分别为[Medusa 种子适配器](../func/功能/Medusa种子适配.py)和[最小验证驱动](../func/测试过程/Medusa双引擎最小验证.py)；逐笔核验程序的源码与 Go 依赖锁定文件位于[回放核验目录](../func/测试过程/Medusa双引擎最小验证/)。

官方核查链接：Medusa [v1.5.1 release](https://github.com/crytic/medusa/releases/tag/v1.5.1)、[Fuzzing configuration](https://github.com/crytic/medusa/blob/v1.5.1/docs/src/project_configuration/fuzzing_config.md)、[Testing configuration](https://github.com/crytic/medusa/blob/v1.5.1/docs/src/project_configuration/testing_config.md)、[Reporting](https://github.com/crytic/medusa/blob/v1.5.1/docs/src/testing/reporting.md)、[corpus loader source](https://github.com/crytic/medusa/blob/v1.5.1/fuzzing/corpus/corpus.go)、[native sequence source](https://github.com/crytic/medusa/blob/v1.5.1/fuzzing/calls/call_sequence.go)。
