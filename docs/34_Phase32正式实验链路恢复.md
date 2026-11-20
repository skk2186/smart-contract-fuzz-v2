# Phase32-R：Pigfox RWA 正式实验链路恢复

日期：2026-11-20  
仓库 HEAD：`895dd55a9ec656c0a6ce1a42447cb74b443a02ac`  
Pigfox 上游提交：`2a6c4b0cfad46d1f84cbd6aaf3a2e0881660b03d`  
状态：E0/E1/E3 的三随机种子对照完成；本轮停止。

## 六项验收问题

1. **为什么 smoke 成功、正式实验失败？** 两次运行使用了逐文件哈希一致的上游业务源码和原 Harness，但构建来源、工作目录与工具链不同。成功的 smoke 从 `/tmp/codex-phase32-rwa` 运行，使用 Foundry 1.4.2 生成的现成 `out/cache`，Echidna 2.2.6 在 `testLimit=40` 下完成 45 次调用。正式目录由 Foundry 1.9.0-dev 在 `sol/真实项目/PigfoxRWATokenDemo` 清理并重建；CryticCompile 0.3.11 和 0.4.2 都无法从 Foundry build-info 解析未落盘的 `foundry-pp/DeployHelper…sol`。将五个虚拟源码物化后，Echidna 2.3.2 又在部署时调用不支持的 `HEVM::deployCode(string,bytes)`（selector `0x29ce9dde`）而退出。原业务源码不是差异来源。
2. **具体修复了什么？** 采用隔离的 `/tmp/phase32-r-native-copy-20261120` 工作树，把原业务合约及 `Actor.sol` 按原字节复制，只替换独立副本中的 `Properties.sol`。使用本机 CryticCompile 0.4.2 与 solc 0.8.28 直接编译，不经过 Foundry 的 DeployHelper/HEVM 部署路径。适配 Harness 只把 `TOKEN`、`holders` 两个 `internal` 状态变量改为 `public`，新增只读 getter；初始化、动作函数和属性函数体保持原样。Anvil 与 Echidna 的 E0/E1/E3 都使用同一适配 Harness、同一属性、固定地址与发送者集。
3. **E0 是否真正跑满 500 配置预算？** 是。第一道门的空语料 E0 达到 `Test limit reached`，日志记录 `fuzzing: 503/500`、总调用 503，并生成 LCOV。之后三个冻结随机种子的 E0 均正常达到预算：`503/500`、`506/500`、`501/500`。这里的 500 是 Echidna `testLimit` 配置，日志中的额外交易调用不解释为独立测试用例数。
4. **E1/E3 是否有有效结果？** 两组都有各自生成的、可执行的语料；Echidna 三个随机种子的 seed-only 和 500 运行均明确加载并回放一条语料。E1 是 Phase32 Agent A/B 原始 `mintToHolder(0, 1e18)`；E3 是既有状态反馈扩展从该输入生成的两次 `mintToHolder(0, 1e18)`。Anvil 观察到属性相关状态变化，但供给求和属性始终为真；所有运行均未触发目标反例。E3 用时 21.159 秒，执行 7 个扩展候选、总计 8 次 Anvil 回放；参数修复规则已启用，但没有提出修复。
5. **是否首次形成一个完整独立项目对照？** 是：Pigfox RWA 的供给求和属性首次形成 E0/E1/E3、每组 3 个固定随机种子的完整可比较运行数据。范围是**一个项目、一个属性、一个经审查的只读观察适配 Harness**，并非未修改上游 Harness 的原生运行，也不足以单独证明方法有收益。
6. **是否可复用于下一个独立项目？** 通用 Echidna/Anvil 运行与属性 getter 观察路径已可复用；遇到相同类型的 Harness 私有状态观察缺口或 Foundry 部署兼容问题时，需要为该项目单独审查并记录只读兼容 Harness。下一个项目未在本轮启动。

## 运行链路与源码核对

原有 smoke 与正式目录的上游提交均为 `2a6c4b0cfad46d1f84cbd6aaf3a2e0881660b03d`。原始 `test/Properties.sol` SHA-256 为 `b7cbfdc57cc4229431705421635b3c6e576e1ed5301fae96ea30a5fd64c2066f`；smoke 副本与正式仓库相同。业务源码、接口、`Actor.sol` 和 `PigfoxProperties.sol` 的逐文件哈希已保存；十二个文件在仓库与 smoke 工作树间完全相同。兼容 Harness SHA-256 为 `2dc2440816d6e21ddd5980a750d448acd58686fc7c97bb28a53c786055599eb6`。属性函数体哈希经比较保持不变。

适配的明确改动只有：

- `RWAToken internal immutable TOKEN` → `RWAToken public immutable TOKEN`；
- `address[NUM_HOLDERS] internal holders` → `address[NUM_HOLDERS] public holders`。

这两项只增加外部只读 ABI getter，不增加写入动作。上游 `/sol/真实项目/PigfoxRWATokenDemo` 下的业务合约和 Harness 均未编辑。临时编译树中业务文件为原字节副本，`foundry.toml` 不存在。修改 diff、源文件哈希、编译命令和编译产物分别见 [兼容 Harness 说明](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/CompatibilityHarness/README.md)、[改动 diff](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/CompatibilityHarness/Properties.diff)、[源文件清单](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/CompatibilityHarness/native-solc-source-manifest.json)、[源码逐文件对照](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/Diagnostics/source-comparison.json)和 [Anvil artifact](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/CompatibilityHarness/RWA-Properties-compat-artifact.json)。

| 环境 | smoke 成功路径 | 原正式路径 | Phase32-R 恢复路径 |
|---|---|---|---|
| 工作目录 | `/tmp/codex-phase32-rwa` | 仓库中的 `sol/真实项目/PigfoxRWATokenDemo` | `/tmp/phase32-r-native-copy-20261120` |
| Echidna | 2.2.6 | 2.3.2 | 2.3.2 |
| Foundry | 1.4.2 | 1.9.0-dev，commit `6056c5845d34205a83cf7108042adb137325c9df` | 不参与 Harness 编译/部署；Anvil 仍为 1.9.0-dev |
| CryticCompile | smoke 既有 build 产物路径 | 0.3.11、0.4.2 均遇到虚拟源码路径；物化后虽可编译，Echidna 部署失败 | 0.4.2，solc 0.8.28 直接编译 |
| Harness 部署路径 | 旧 Foundry 构建产物 | Foundry 生成的 `HEVM::deployCode` 路径 | Solidity 原生构造部署；不调用 `HEVM::deployCode` |
| 结果 | `testLimit=40`；45 次调用，8,990 unique instructions | fuzz 前失败；无有效 LCOV 对照 | E0 三次空语料 500；E1/E3 各三次 seed-only 与 500 |

本机已有 CryticCompile 0.3.11（`/home/skk/miniconda3/envs/contract-fuzz`）和 0.4.2（`.tools/olympia-venv`），没有覆盖现有环境；两者在隔离 Foundry 1.9.0 构建副本上的结果及物化后的调用路径见 [兼容性对照日志](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/Diagnostics/toolchain-comparison.json)、[0.3.11 日志](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/Diagnostics/crytic-compile-0.3.11-foundry-1.9.0.log)、[0.4.2 日志](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/Diagnostics/crytic-compile-0.4.2-foundry-1.9.0.log)及 [物化源码日志](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/Diagnostics/foundry-pp-materialized-manifest.json)。Echidna 的 HEVM 部署失败保留在 [Phase32 原始日志](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-20261120/Diagnostics/RWA-materialized-ignore-compile-one-test/echidna.log)；旧 Phase32 文件未覆盖。

本轮 E0/E1/E3 环境为 Echidna 2.3.2、CryticCompile 0.4.2、solc 0.8.28、Anvil 1.9.0-dev；优化器启用 200 runs、EVM Cancun、单 worker、序列长度 8、shrinkLimit 1、chainId 1、固定部署地址 `0xa647ff3c36cFab592509E13860ab8c4F28781a66`、property sender 和五个 sender 与 Phase32 冻结配置一致。兼容 Harness 的直接 CryticCompile 命令为：

```text
crytic-compile test/Properties.sol --compile-force-framework solc \
  --solc /home/skk/.solc-select/artifacts/solc-0.8.28/solc-0.8.28 \
  --solc-args "--base-path . --optimize --optimize-runs 200 --evm-version cancun"
```

命令在隔离工作树中返回 0。每次 Echidna 调用的完整 argv、cwd、版本、yaml、退出码、日志、LCOV 和运行时均保存于 [实验结果目录](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/)；可复现驱动为 [Phase32R正式实验.py](../func/测试过程/SCFuzzBench公开项目接入/Phase32R正式实验.py)。E0 首道门原始日志见 [E0 500 空语料日志](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/E0/seed-20261125-attempt3/echidna.log)。

## 属性状态观察修复

RWA 供给求和属性实际读取：

```solidity
TOKEN.balanceOf(address(this))
TOKEN.balanceOf(PHANTOM)
TOKEN.balanceOf(holders[i])  // i = 0..NUM_HOLDERS-1
TOKEN.totalSupply()
```

`mintToHolder(0, 1e18)` 成功后，Anvil trace 显示 RWAToken 发出 `Transfer(0x0, holders[0], 1e18)`；公开 getter 逐笔给出 `totalSupply: 0 → 1e18`、`balanceOf(holders[0]): 0 → 1e18`。`address(this)`、`PHANTOM` 与 holders[1..3] 的余额仍为 0，目标属性交易前后均为 `true`。这正是“属性恒真但组成变量已变化”的有效种子情形。

先前观察器同时存在三个通用缺陷：项目相对源码引用只从仓库根目录解析，无法找到 `test/Properties.sol`；Harness 的 `TOKEN`、`holders` 为 `internal`，ABI 没有对应 getter；观察器不能把 `holders[i]` 展开为有界数组 getter 读取，因此跨合约 `balanceOf(holders[i])` 被跳过。新修复让观察器按项目源码根目录解析属性、通过公共索引 getter 解析 `name[index]`、在已静态界定且最多 256 项的循环内展开嵌套跨合约调用；缺少 receiver getter/ABI 或发生 getter 调用错误时保留 `unresolved`/`call_error`，将状态归为不可观察，而不再静默判成“未变化”。

完整逐笔初值、交易后值、getter 地址与参数、布尔属性值及差分记录见 [E1 Anvil 回放](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/Observer/E1逐笔属性状态对照.json)和 [观察器摘要](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/Observer/validation-summary.json)。

## E0/E1/E3 最小完整对照

三个随机种子均为冻结值 `20261125 / 20261135 / 20261145`。每组先运行 `testLimit=0` seed-only 阶段，再运行 `testLimit=500`；E0 使用空语料，E1/E3 各使用自身的有效语料。E1 复用 Phase32 原始 A/B 候选，不调用 Agent；E3 只启用既有 `state_feedback` 模式，不执行 R/S，也不改变扩展算法、排序或预算。Echidna 完整矩阵包含 18 次运行，所有运行退出码均为 0，九次 500 运行均到达预算。

| 组 | 每 seed seed-only LCOV 行 | 每 seed 500 后新增行 | 最终 LCOV 行（按 seed） | 500 阶段实际调用（按 seed） | 500 阶段平均时间 | 外部语料证据 | 属性反例 |
|---|---:|---:|---|---|---:|---|---|
| E0 空语料 | 58 | 202 / 202 / 200 | 260 / 260 / 258 | 503 / 506 / 501 | 1.787 秒 | 空语料；无加载、无重放 | 0/3 |
| E1 原始 A/B | 82 | 178 / 178 / 178 | 260 / 260 / 260 | 502 / 508 / 508 | 1.795 秒 | 每 seed 加载 1 条并重放 1 条 | 0/3 |
| E3 A/B+状态反馈扩展 | 82 | 178 / 178 / 178 | 260 / 260 / 260 | 506 / 506 / 505 | 2.176 秒 | 每 seed 加载 1 条并重放 1 条 | 0/3 |

LCOV 数值为 Echidna 输出 LCOV 中执行行的去重集合大小。E1/E3 seed-only 比 E0 多 24 行；继续 500 后三组最终覆盖基本相同，E1/E3 均为 260 行，E0 为 258–260 行。因此本轮证明的是链路恢复和数据可比较，**没有观察到 E1/E3 的最终覆盖收益或目标反例优势**。E3 与 E1 的种子单独回放覆盖相同，且两种 seeded fuzz 的新增行均为 178 行。

E3 通过 `state_supported_repetition` 生成了两笔 `mintToHolder(0, 1e18)` 的独立扩展序列；Anvil 验证目标属性仍为真且相关余额/供给状态发生变化。扩展过程执行 7 个候选、总计 8 次 Anvil 回放，用时 21.159173 秒；未提出参数修复。原始 Agent A/B 两次 API 调用共 30,052 tokens（29,488 输入、564 输出），该历史属性流程耗时 5.485 秒，估算费用为非高峰 `$0.004611072`、高峰 `$0.009222144`。本轮新增 Agent API 调用数为 0。分组运行详情和种子成本分别见 [Echidna matrix](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/Echidna/matrix.json)、[E3 扩展记录](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/E3/Extension/E3-扩展回放.json)及 [种子成本记录](../func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120/seed-preparation-costs.json)。

## 结果边界与停止状态

- 这是一项由独立上游项目产生的完整单项目对照，但运行对象是所有组共用的只读兼容 Harness。不能称为“未修改上游 Harness 原生实验”。
- 供给求和属性在 Anvil 和 Echidna 中均未被违反；E1/E3 的价值证据是组成状态确实改变且被观察，而不是发现漏洞。
- 该三组结果不能支持扩大样本的收益主张。Phase32 原始报告、冻结任务及其失败日志全部保留；本报告作为 Phase32-R 补充，不回写旧结果。
- 通用观察器与 Echidna 的 direct-solc 运行条件已可带到下一个独立项目。若其 Harness 仍依赖 Echidna 不支持的 cheatcode，需要按同样原则先做语义审查和独立只读适配，再运行所有配对组。下一项目未启动。

本轮工作已完成并停止；没有自动启动新项目、没有提交或推送。
