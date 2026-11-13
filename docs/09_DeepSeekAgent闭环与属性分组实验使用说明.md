# DeepSeek Agent A/B 闭环与属性分组实验使用说明

更新日期：2026-11-13

## 1. 内容与文件

本说明记录 DeepSeek `deepseek-flash`、Agent A/B、EVM 逐交易回放和 Echidna 2.3.2 原生语料的用法，以及 Request、Immutable 的分组成本闭环实验。

目录按用途分开：

- `deepseek/`：DeepSeek 接口、Agent A/B、实验脚本及模型调用结果。
- `func/功能/`：Slither 属性分析、上下文适配、种子验证等核心功能。
- `func/测试过程/`：适配器与属性分组回归测试、预处理计时脚本。

DeepSeek 调用记录和实验结果在 `deepseek/结果/`；Slither 分析输入仍在 `.tools/results/`。密钥由环境变量 `DEEPSEEK_API_KEY` 或本机 `.tools/deepseek.key` 提供；不要把密钥写入代码、报告或版本库。

## 2. 环境与单属性运行

已验证环境为 Ubuntu 20.04、Python 3.11.15、Web3.py 7.16.0、eth-abi 5.2.0、Echidna 2.3.2，以及项目内 Anvil。下面的命令在项目根目录执行：

```bash
export PYTHONPATH=func/功能:deepseek
PYTHON=/home/skk/miniconda3/envs/contract-fuzz/bin/python
```

检查 Agent 命令：

```bash
$PYTHON deepseek/实验过程/运行Agent种子流程.py --help
```

用 Request 的 `echidna_token_conservation` 运行一个属性的示例：

```bash
$PYTHON deepseek/实验过程/运行Agent种子流程.py Request \
  --property-contains echidna_token_conservation \
  --max-candidates 1 --max-steps 5 --repairs 1 \
  --echidna-limit 100 --echidna-timeout 45
```

流程会执行 Agent A、Agent B、ABI 校验、Anvil 逐笔回放，再把可用种子交给 Echidna。结果写入 `deepseek/结果/Request-Agent种子闭环.json`。如只想检查前面环节，可添加 `--skip-echidna`。

三个固定属性的 API/JSON smoke 命令为：

```bash
$PYTHON deepseek/实验过程/测试DeepSeek接口.py
```

它覆盖 Hokusai、Request、Immutable 各一个已有属性，结果写入 `deepseek/结果/DeepSeek接口固定属性测试.json`。本轮已运行通过；再次运行会产生新的 API 用量。

## 3. 正式分组实验命令

主矩阵对 Request 3 属性组和 Immutable 18 属性组各重复 3 次：

```bash
$PYTHON deepseek/实验过程/分组闭环实验.py \
  --projects Request Immutable \
  --repetitions 3 --test-limit 100 --process-timeout 45
```

随后补同预算的空语料原生 Echidna、配对随机参数种子，并重复计时预处理阶段：

```bash
$PYTHON deepseek/实验过程/分组闭环实验.py \
  --augment-existing --test-limit 100 --process-timeout 45 \
  --preprocess-repetitions 10
```

第二条命令不调用 DeepSeek；它会执行本地 Echidna/Anvil 对照、覆盖新增实验报告。每次补测使用新的独立 Echidna 目录，避免上轮变异语料进入下一轮的外部种子统计。

四种 Agent A 条件为：

| 条件 | 输入批次 |
|---|---|
| `independent` | 每属性单独输入 |
| `random_batch` | 随机打批，Request 每批 2 条、Immutable 每批 3 条 |
| `associated` | 当前属性关联组整体输入，规模分别为 3 和 18 |
| `controlled_size` | 按属性 ID 排序后按 2/3 条受控分批，与随机批次规模一致 |

相同条件下使用同一个模型、属性集合、提示要求、每属性最多 1 个候选、最多 5 笔交易。Agent B 和 Anvil 只对预先登记的样本属性运行：Request 每轮 1 条，Immutable 每轮 3 条。Echidna 则对各 Harness 中全部 `echidna_*` 属性运行，不因分组改变测试目标。`random_batch` 的参数基线保持 Agent A 函数序列和交易数，只随机化 ABI 参数和发送者。

## 4. 结果文件与证据

正式结果：`deepseek/结果/DeepSeek分组闭环实验.json`。其中保留每次 API 用量、响应、种子、回放、Echidna 输出、异常、属性失败归因和计时样本。报告约 1.3 MB，原始日志未删减。

Echidna 是否使用外部语料按日志中的正数 `Loaded N transaction sequences from .../coverage` 判断；是否回放检查 `Sequence replayed from corpus file`；后续是否变异检查 `fuzzing:` 状态和 `Unique instructions`。`Loaded 0` 不算种子加载。本轮有效外部语料的 Echidna 运行均观察到加载、回放和变异证据。

Anvil 在每笔交易后检查交易执行、目标属性及 Harness 中的 `echidna_*` 谓词。预验证时已为假的属性会记入 `prevalidation_violations`，不计为 Echidna 变异发现。带 `no transactions made` 的失败单列为初始状态失败。

## 5. 实测结果

下表中的 Agent A Token 是 DeepSeek API 返回的实际提示 Token，用量/费用跨 3 次重复取中位数。费用为 Agent A+B 峰时价格估算，不含单独的缓存探针。Echidna 列表示 3 次中观察到的外部语料加载、回放和变异次数。

| 项目 | 条件 | Agent A 输入 Token | A 输出覆盖 | Agent B 可回放 | Echidna 加载/回放/变异 | A+B 峰时费用中位数 |
|---|---|---:|---:|---:|---:|---:|
| Request | 独立 | 9,955 | 3/3 | 3/3 | 3/3 / 3/3 / 3/3 | $0.004237 |
| Request | 随机批处理 | 8,395 | 3/3 | 3/3 | 3/3 / 3/3 / 3/3 | $0.004010 |
| Request | 关联分组 | 6,835 | 3/3 | 3/3 | 3/3 / 3/3 / 3/3 | $0.003659 |
| Request | 受控组规模 | 8,395 | 3/3 | 3/3 | 3/3 / 3/3 / 3/3 | $0.003929 |
| Immutable | 独立 | 36,781 | 18/18、18/18、18/18 | 9/9 | 3/3 / 3/3 / 3/3 | $0.033821 |
| Immutable | 随机批处理 | 29,401 | 18/18、18/18、16/18 | 8/9 | 3/3 / 3/3 / 3/3 | $0.036866 |
| Immutable | 关联分组 | 26,326 | 0/18、18/18、0/18 | 3/9 | 1/3 / 1/3 / 3/3 | $0.010316 |
| Immutable | 受控组规模 | 29,401 | 18/18、18/18、18/18 | 9/9 | 3/3 / 3/3 / 3/3 | $0.031621 |

Request 的关联分组比独立输入少 31.3% 的 Agent A 提示 Token，3 次均输出覆盖全部 3 个属性；本预算下四种方式的 Echidna 均未报告属性失败。

Immutable 关联组提示 Token 比独立输入少 28.4%，但完整 18 属性输入只有 1/3 次覆盖全部属性，另两次没有候选，不能据此声称成本收益成立。受控 3 属性组相对独立输入少 20.1% 提示 Token，三次均覆盖 18 个属性，Agent B 样本回放为 9/9。随机参数基线方面，Request 为 12/12 可回放；Immutable 为 29 条都发生交易回滚，说明它未满足该项目相应交易约束。

### Echidna 结果解释

- Request 的原生 Echidna、Agent 种子和随机参数种子在 100 测试预算内均无属性失败。
- Immutable 的原生空语料运行在三次重复中都报告 9 条 `failed with no transactions made`。这些是 Harness 初始状态已经违反的属性，不是本实验发现的变异反例。
- Immutable 的 Agent 种子回放中，五个其他属性在 Echidna 变异前已由 Anvil 观察到失败。Echidna 运行中的这些重叠失败不记作变异收益。
- `echidna_token_id_uniqueness` 在至少一次运行中作为非初始状态失败出现，Anvil 对已选种子的预验证未观察到它。报告保留完整轨迹；在完成反例去重、最小化与原因核验前，不把它宣称为新的独立漏洞。
- 关联分组大组偶发没有候选输出；结果按失败保留，未重跑挑选成功响应。

### 预处理与本地 Token 编码

每个项目对已生成的 Slither JSON 重复 10 次。下表为中位数（波动范围，单位毫秒）；不包括 Solidity 编译、Slither 全程序分析或 Agent 网络等待。Token 编码使用本地 `tiktoken 0.14.0 / o200k_base`，只用于同一布局间比较，DeepSeek 的正式 Token 数采用 API 实际 usage。

| 项目 | 特征提取 | 依赖图构建 | 属性合并 | 上下文去重 | 本地编码：独立 / 全局共享 / 分组 |
|---|---:|---:|---:|---:|---:|
| Hokusai | 0.59 (0.44–1.35) | 0.83 (0.62–1.52) | 0.42 (0.36–0.74) | 290.02 (252.10–374.84) | 759.99 (700.12–796.56) / 288.97 (260.50–330.37) / 677.06 (628.90–770.39) |
| Request | 0.08 (0.08–0.15) | 0.14 (0.13–0.18) | 0.09 (0.09–0.13) | 47.20 (43.96–50.65) | 117.33 (114.20–122.92) / 17.99 (17.31–18.40) / 77.20 (74.02–81.40) |
| Immutable | 0.13 (0.08–0.15) | 0.64 (0.60–0.74) | 0.87 (0.80–0.96) | 10.72 (9.81–11.40) | 57.86 (55.99–61.00) / 19.70 (18.76–20.62) / 25.65 (24.34–27.28) |

三种等价上下文布局的本地 Token 总数为：

| 项目 | 逐属性独立 | 全项目共享目录 | 关联分组 |
|---|---:|---:|---:|
| Hokusai（101 属性） | 3,950,565 | 1,383,857 | 3,476,303 |
| Request（16 属性） | 675,493 | 100,153 | 438,356 |
| Immutable（32 属性） | 304,591 | 107,247 | 135,705 |

关联分组相对逐属性独立输入的本地 Token 减少比例分别为 Hokusai 12.0%、Request 35.1%、Immutable 55.4%。全项目共享目录只用于上下文压缩测量，不等同于 Agent 每次请求的分组策略。

DeepSeek 自动缓存探针每项目每轮对独立模式中的一个属性重复发送相同请求，API 返回的命中输入 Token 比例约为 Request 94.3%、Immutable 94.7%。该探针单独记录，不计入表中候选质量和费用。API 没有在本实现中提供可控的“关闭缓存”请求，因此这些数据不是缓存开/关的随机对照。

## 6. 限制与复现注意事项

1. 正式 Agent/EVM 矩阵只包含 Request 和 Immutable。Hokusai AMM 关联组所需的 `EchidnaAMMGraduation.sol` 和编译 Harness 不在当前工作区快照中，所以未用它声称真实闭环结果；Hokusai 只进入静态上下文与预处理计时。
2. Agent B/EVM 只检查预先指定的一小组属性，并非 Request 3 条、Immutable 18 条全量实例化。Echidna 仍测试各 Harness 的全部 16/32 条属性。
3. 随机参数基线只适用于适配器支持的整数、地址和布尔 ABI 参数。其他 ABI 类型不会被静默转换。
4. Immutable Harness 存在初始状态已失败的原生属性，降低了当前反例发现率对比的解释力；应先核查属性和 Harness 初始化语义，再扩大正式结论。
5. DeepSeek 费用按 API 用量与官方单价估算。价格会变动；官方价格表当前列出的 `deepseek-flash` 峰时输入缓存命中、未命中和输出价格分别为每百万 Token $0.006、$0.30 和 $1.20，非峰时为峰时的一半：[DeepSeek 模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)。

正式矩阵 A/B 共计峰时估算 $0.403466，另加缓存探针约 $0.002381；单独的三个固定属性 smoke 调用未计入该金额。API 价格与实际扣费时间段不同会造成账单差异。
