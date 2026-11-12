# Echidna 论文最小复现：Slither 预处理与多交易反例

本目录只保留一个可运行合约和本使用文档。复现对象暂按 Grieco 等人的 [ISSTA 2020 Echidna 论文](https://agroce.github.io/issta20.pdf) 确定；若研究对象是另一篇论文，需要重新核对实验范围。

## 复现范围

论文第 2.1 节描述：Echidna 在模糊测试前调用 Slither 编译并分析合约，提取常量及直接处理 ETH 的函数，再依据 ABI、常量和语料生成交易。这里复现图 2(a) 的两步状态场景，并检查当前 Slither 的实际输出、Echidna 是否调用 Slither、以及是否发现两笔交易的反例。

`PaperExample.sol` 保留了图 2(a) 的条件和属性。为使用本机已有的 Solidity 0.8.20 编译器，两个 setter 删除了论文示例中未使用的 `bool` 返回值，属性函数加了 `view`；状态转移和违反条件不变。

这是**功能性小样本复现**。论文第 4 节的 VeriSmart/Tether 样本、MythX/solfuzz 对照、重复运行和覆盖率曲线没有在此复现；下面的结果不能替代论文实验，也不能推断 Slither 的平均性能收益。

## 环境

本机已核验：Echidna 2.3.2、Slither 0.11.5、Solidity 0.8.20。以下命令在 WSL Ubuntu 的 `/home/skk/smart-contract-fuzz-v2` 执行，使用现成的 `contract-fuzz` 环境，无需安装或修改全局编译器版本。

```bash
cd /home/skk/smart-contract-fuzz-v2
export PATH="$HOME/miniconda3/envs/contract-fuzz/bin:$PATH"
export SOLC_VERSION=0.8.20
echidna --version
slither --version
solc --version
```

换一台机器时，需要先确保 `echidna`、`slither` 和兼容的 `solc` 都在 `PATH` 中。Echidna 的[官方安装说明](https://github.com/crytic/echidna#installation)提供其他安装方式；这里没有安装新工具。

## 重点：如何使用 Slither

```bash
# 1. 查看函数读写的状态变量。
slither PaperExample.sol --print function-summary

# 2. 查看 Echidna 专用的结构化预处理信息。
slither PaperExample.sol --print echidna

# 3. 查看中间表示中的实际条件。
slither PaperExample.sol --print slithir

# 4. 可选：查看变量数据依赖；不要将其等同于控制依赖。
slither PaperExample.sol --print data-dependency
```

在本机的 `function-summary` 输出中，`set0` 写 `flag0`，`set1` 读 `flag0`、写 `flag1`，`echidna_flag` 读 `flag1`。`--print echidna` 输出包含 `constants_used` 中的 23、100、5、10，以及 `functions_relations` 中的 `set0(int256) → set1(int256) → echidna_flag()`。`payable` 为空，因为这个例子没有收取 ETH 的函数。`slithir` 能看到 `val % 100 == 23` 和 `val % 10 == 5 && flag0`。

**区分论文和当前工具版本：**论文明确描述了 Slither 对常量和 ETH 函数的提取；本机 Slither 0.11.5 的 Echidna printer 还给出了函数关系等字段。这是当前工具的实测输出，不应倒推为 2020 年论文版本已有同样字段。`data-dependency` 的输出也不能单独证明 `flag0` 对 `flag1` 的条件控制关系；函数关系只提供静态候选，不能证明某条交易序列可执行。

## 运行 Echidna

```bash
# 默认启用 Slither；单工作线程和固定随机种子便于重跑。
echidna PaperExample.sol --contract TEST --format text \
  --test-limit 10000 --seq-len 10 --workers 1 --seed 42 --shrink-limit 200

# 仅作功能对照：同样参数，关闭 Slither。
echidna PaperExample.sol --contract TEST --format text \
  --test-limit 10000 --seq-len 10 --workers 1 --seed 42 --shrink-limit 200 \
  --disable-slither
```

启用时，启动日志应出现 `Running slither on ... Done!`；关闭时会出现 Slither 被禁用的警告。属性违反时，最终报告包含 `echidna_flag: failed` 和缩减后的 `set0(...)`、`set1(...)` 两笔交易。可自行检查第一笔参数满足 `% 100 == 23`，第二笔满足 `% 10 == 5`。发现反例时 Echidna 可能返回非零退出码，这不表示编译失败。

本机一次固定配置运行的观测如下。`Total calls` 是 Echidna 报告值，不是统计均值；两种配置都找到了反例。

| 配置 | Slither 调用 | 属性结果 | 报告的 Total calls | 缩减后交易数 |
| --- | --- | --- | ---: | ---: |
| 默认 | 成功 | failed | 1,667 | 2 |
| `--disable-slither` | 禁用 | failed | 8,626 | 2 |

单一合约、单一随机种子、单次运行只能验证流程。两行调用数不能作为 Slither 加速的研究结论；对照还需多随机种子、相同版本与机器、时间和预处理开销记录，并在真实合约上重复。

## 对 V2 的直接启示

当前 Slither 已提供 Echidna 专用的函数关系和常量信息，V2 开始设计属性依赖适配层时应先复用并评估这些现有输出，再识别缺少的调用者、参数、mapping 和跨合约语义。Slither 的静态关系与 Echidna 的实际执行结果需要分开记录。

资料：[论文原文](https://agroce.github.io/issta20.pdf) · [Echidna 官方仓库](https://github.com/crytic/echidna) · [Echidna 配置说明](https://secure-contracts.com/program-analysis/echidna/configuration.html)
