# Echidna 2.3.2 原生多交易种子验证

## 对象与种子

使用 Hokusai Token 固定提交 [`f133747`](https://github.com/Hokusai-protocol/hokusai-token/blob/f133747acd3587e55020f7bcd9470afa898789cb/contracts/echidna/EchidnaHokusaiToken.sol) 的原生 `EchidnaHokusaiToken` Harness，重点观察 `echidna_supply_accounting` 与 `echidna_investor_cap`。本机 `echidna --version` 输出 `Echidna 2.3.2`。手工语料为 [`seeds/Hokusai手工多交易种子.txt`](../seeds/Hokusai手工多交易种子.txt)，按本机 2.3.2 实际生成的 `coverage/*.txt` 格式编写；格式与 Echidna [官方语料说明](https://github.com/crytic/building-secure-contracts/blob/master/program-analysis/echidna/advanced/collecting-a-corpus.md)一致。

| 顺序 | 外部函数与参数 | 发送者 | 目标 |
| --- | --- | --- | --- |
| 1 | `mintInvestorSelf(1000000000000000000)` | `0x0000000000000000000000000000000000010000` | Harness |
| 2 | `mintInvestorUserA(2000000000000000000)` | `0x0000000000000000000000000000000000020000` | Harness |
| 3 | `burnInvestorUserA(1000000000000000000)` | `0x0000000000000000000000000000000000030000` | Harness |

三笔都是独立外部交易，`value=0`，`gas=12500000`。构造时固定了函数、ABI 参数、发送者、调用目标和延迟，没有用单笔 Harness 包装替代交易边界。源码中的 `_bound(value,maxValue)` 返回 `(value % maxValue)+1`，所以交易实际产生的内部数量与传入数量相差 1 wei；这一点由下述状态回放核对。

## 命令与结果

完整 Hokusai 项目已按原生 Hardhat 配置编译。以下在 V2 根目录执行，`HOKUSAI` 指向固定提交的完整项目；测试规模仅用于验证接口行为，不构成模糊测试效果实验。

```bash
export PATH="$PWD/.tools/node/bin:$PWD/.tools/hokusai/node_modules/.bin:$HOME/miniconda3/envs/contract-fuzz/bin:/usr/local/bin:$PATH"
HOKUSAI=/tmp/adapter-sixth-20261112/hokusai-token-f133747acd3587e55020f7bcd9470afa898789cb
mkdir -p .tools/seed-default/coverage .tools/seed-mutation/coverage .tools/no-seed-control
cp seeds/Hokusai手工多交易种子.txt .tools/seed-default/coverage/manual.txt
cp seeds/Hokusai手工多交易种子.txt .tools/seed-mutation/coverage/manual.txt

(cd "$HOKUSAI" && echidna . --contract EchidnaHokusaiToken \
  --config echidna.config.yaml --crytic-args "--hardhat-ignore-compile" \
  --corpus-dir "$OLDPWD/.tools/seed-default" --test-limit 0 --seq-len 3 \
  --timeout 40 --format text)

(cd "$HOKUSAI" && NODE_PATH="$OLDPWD/.tools/hokusai/node_modules" \
  hardhat run --no-compile "$OLDPWD/func/验证Hokusai手工种子.js")

(cd "$HOKUSAI" && echidna . --contract EchidnaHokusaiToken \
  --config echidna.config.yaml --crytic-args "--hardhat-ignore-compile" \
  --corpus-dir "$OLDPWD/.tools/seed-mutation" --test-limit 500 --seq-len 3 \
  --seed 123456 --timeout 30 --disable-slither --format text)

(cd "$HOKUSAI" && echidna . --contract EchidnaHokusaiToken \
  --config echidna.config.yaml --crytic-args "--hardhat-ignore-compile" \
  --corpus-dir "$OLDPWD/.tools/no-seed-control" --test-limit 500 --seq-len 3 \
  --seed 123456 --timeout 30 --disable-slither --format text)
```

**加载与回放。** 启用 Slither 的零随机预算运行记录 `Loaded 1 transaction sequences from .../coverage`、`Sequence replayed from corpus file manual.txt (1/1)`；Echidna 保存的回放文件 `.tools/seed-default/coverage/6911184727885949452.txt` 含完全相同的三笔函数、参数及发送者。五条原生属性均报告 `passing`。该运行状态还显示 `fuzzing: 4/0`，因此不能把整个覆盖报告都归因于手工种子；精确回放的依据是加载日志及相同的保存序列。

**真实状态。** [`func/验证Hokusai手工种子.js`](../func/验证Hokusai手工种子.js)在完整项目的原生 Hardhat 网络中，以种子指定的三个地址发送相同交易并读取合约状态。所有交易成功；`investorMinted=2000000000000000001`、`totalSupply=2000000000000000001`、`USER_A` 余额 `1000000000000000000`、Harness 余额 `1000000000000000001`，两条目标属性返回 `true`。Hardhat 与 Echidna 是不同 EVM 实现，这一步独立确认交易参数和状态转移可行；Echidna 自身的回放由上述日志确认。

**后续变异。** 为单独观察语料机制，固定 `--seed 123456`、`--test-limit 500`，并在有种子及对照两次运行中均禁用 Slither 引导。Echidna 首先加载并回放 `manual.txt`，随后保存 `.tools/seed-mutation/coverage/7261756948625281014.txt`：其前两笔调用的函数、参数和发送者与手工种子完全一致，第二笔的延迟发生变化，第三笔由 `burnInvestorUserA` 变为 `attemptUnauthorizedMint`。本次有种子运行输出 `fuzzing: 501/500`、语料 9 条；相同随机设置的无种子对照加载 0 条、语料 8 条，其保存语料中没有精确参数 `2000000000000000000`。这些观测与 Echidna [官方 FAQ 所述的语料回放和变异机制](https://github.com/crytic/building-secure-contracts/blob/master/program-analysis/echidna/frequently_asked_questions.md)一致，支持种子被实际用于后续变异；不把语料条数差异视为性能收益。两次运行最终覆盖均为 4864 条指令，没有发现属性违反。

运行日志在 `.tools/results/Hokusai默认配置回放.log`、`.tools/results/Hokusai种子变异运行.log`、`.tools/results/Hokusai无种子对照.log`；相关语料保留在 `.tools/seed-default`、`.tools/seed-mutation`、`.tools/no-seed-control`。首次运行这些命令时应使用空语料目录，重跑可换新目录。Hokusai 原配置中的 `solcVersion` 被 Echidna 2.3.2 提示为 `unused option`，实际编译通过原项目 Hardhat 产物与 `--hardhat-ignore-compile` 完成；没有为消除警告修改原项目配置。
