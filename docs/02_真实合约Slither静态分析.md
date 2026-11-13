# 真实合约的 Slither 静态分析与属性条件化入口检查

分析日期：2026-11-11。目的仅是判断现有 Slither 输出能否为下一步**属性条件化分析**提供可靠的起点；本次没有运行模糊测试，也没有把静态关系当作可执行交易序列。

## 样本与来源

| 样本 | 本地文件 | 上游来源 | 属性来源 |
| --- | --- | --- | --- |
| WETH9，真实使用的 ETH 包装合约 | `sol/单合约测试/WETH9/WETH9原始合约.sol` | [gnosis/canonical-weth，固定提交](https://github.com/gnosis/canonical-weth/blob/0dd1ea3e295eef916d0c6223ec63141137d22d67/contracts/WETH9.sol) | 原始源码无 `echidna_*`；`sol/单合约测试/WETH9/WETH9属性适配.sol` 是本次新增的分析夹具 |
| DSToken，Dapphub 的 ERC20 合约 | `sol/单合约测试/DSToken/DSToken原始合约.sol` | [dapphub/ds-token，固定提交](https://github.com/dapphub/ds-token/blob/16f187acc15dd839589be60173ad1ebd0716eb82/src/token.sol) | 原始源码无 `echidna_*`；`sol/单合约测试/DSToken/DSToken属性适配.sol` 是本次新增的分析夹具 |

DSToken 的原始导入分别保存在 `sol/单合约测试/DSToken/ds-auth/auth.sol` 和 `sol/单合约测试/DSToken/ds-math/math.sol`，来源为 [ds-auth](https://github.com/dapphub/ds-auth/blob/a51e7caa1f03eeffed66d67f3b38605e0f1f881d/src/auth.sol) 与 [ds-math](https://github.com/dapphub/ds-math/blob/e70a364787804c1ded9801ed6c27b440a86ebd32/src/math.sol)。这两个依赖取上述固定提交，尚未核对是否与 ds-token 当时的子模块锁定提交一致。四份上游 Solidity 文件保持源内容，`git hash-object` 值依次是 WETH9 `3660ff2fa46c608843a6732244cbfd5833775908`、DSToken `240f704150d4d3766cc39da4081c0a79b0d343cf`、ds-auth `3818735867f6c1e0b3dde3f8597262e7d9c675cb`、ds-math `5ea5761af2dbcf43b9b6dc5505181cf970a5a5b2`。WETH9 原文件附有 GPL-3.0 全文；适配文件明确标为新增，不能当作上游自带属性。

两个适配文件各有两个**诊断用**显式属性：`echidna_actor_balance_within_supply()` 和 `echidna_zero_address_empty()`。后一项在这两个合约中可能被转账到零地址证伪；它用于检查静态关联，不代表项目方作出的安全承诺，也不适合作为未经审核的论文基准属性。

## 环境与实际命令

已有环境：Slither `0.11.5`，`solc 0.4.25`，Python 3.11。未安装工具，也没有改变全局 `solc-select` 版本。以下命令在 V2 项目根目录的 WSL shell 中执行：

```bash
cd "$HOME/smart-contract-fuzz-v2"
export PATH="$HOME/miniconda3/envs/contract-fuzz/bin:$PATH"
export SOLC_VERSION=0.4.25
slither --version
solc --version

# 先检查上游原始文件能否编译，以及是否已有显式属性。
slither sol/单合约测试/WETH9/WETH9原始合约.sol --print echidna
slither sol/单合约测试/DSToken/DSToken原始合约.sol \
  --solc-remaps "ds-math/=sol/单合约测试/DSToken/ds-math/ ds-auth/=sol/单合约测试/DSToken/ds-auth/" --print echidna

# 再分析只添加属性的适配文件。
slither sol/单合约测试/WETH9/WETH9属性适配.sol --print function-summary
slither sol/单合约测试/WETH9/WETH9属性适配.sol --print echidna
slither sol/单合约测试/WETH9/WETH9属性适配.sol --print slithir

slither sol/单合约测试/DSToken/DSToken属性适配.sol \
  --solc-remaps "ds-math/=sol/单合约测试/DSToken/ds-math/ ds-auth/=sol/单合约测试/DSToken/ds-auth/" --print function-summary
slither sol/单合约测试/DSToken/DSToken属性适配.sol \
  --solc-remaps "ds-math/=sol/单合约测试/DSToken/ds-math/ ds-auth/=sol/单合约测试/DSToken/ds-auth/" --print echidna
slither sol/单合约测试/DSToken/DSToken属性适配.sol \
  --solc-remaps "ds-math/=sol/单合约测试/DSToken/ds-math/ ds-auth/=sol/单合约测试/DSToken/ds-auth/" --print vars-and-auth
```

若需程序化读取，使用 `--print echidna --json /tmp/分析结果.json`。该 JSON 的 `results.printers[0].description` **本身还是一个 JSON 字符串**，须再次 `json.loads`，然后读取目标合约的 `functions_relations`、`constants_used`、`payable` 等字段。Slither 运行可能在项目根目录生成 `crytic-export/` 编译中间物；本次没有保留此类临时产物。

## 遇到的问题与解决方法

1. **编译器版本不匹配。** 上次论文示例使用 0.8.20；这两份真实源码属于 0.4.x 语法。使用已安装的 `SOLC_VERSION=0.4.25`，没有修改源码的 pragma 或全局编译器设置。两份原始源码及适配文件随后均由 Slither 成功分析。
2. **DSToken 的包导入找不到。** 直接运行时报 `Source "ds-math/math.sol" not found` 和 `Source "ds-auth/auth.sol" not found`。保留上游导入写法，把两个依赖放入 `sol` 后，使用单个 `--solc-remaps "ds-math/=sol/单合约测试/DSToken/ds-math/ ds-auth/=sol/单合约测试/DSToken/ds-auth/"` 传入两条映射。重复写两次 `--solc-remaps` 会使后一次覆盖前一次，仍编译失败。
3. **上游原始合约没有显式 Echidna 属性。** `--print echidna` 为目标合约分别列出 7 个和 18 个函数关系节点，但 `echidna_*` 属性数均为 0。为验证分析接口，在独立适配文件中各加入两个诊断属性；这只能验证“有属性时 Slither 能输出什么”，不能把样本说成原生多属性协议测试套件。

## 实测结果

| 检查项 | WETH9 属性适配 | DSToken 属性适配 |
| --- | --- | --- |
| Slither 编译/分析 | 成功，2 个合约（含继承） | 成功，6 个合约（含导入与继承） |
| 显式属性识别 | 2 个 | 2 个 |
| 属性读取的主要状态 | `balanceOf`；第一个属性还调用 `totalSupply()`，其值来自合约 ETH 余额 | `balanceOf`；第一个属性还读 `totalSupply` |
| `echidna_actor_balance_within_supply` 的 `is_impacted_by` | `()`（回退函数）、`deposit`、`withdraw`、`transfer`、`transferFrom` | `transfer`、`transferFrom`、`push`、`pull`、`move`、两个重载 `mint`、两个重载 `burn` |
| `echidna_zero_address_empty` 的候选 | 与上一属性完全相同 | 与上一属性完全相同 |
| ETH/权限信息 | `payable` 标出回退函数和 `deposit`；`function-summary` 标出 `msg.value`、`msg.sender.transfer` | `function-summary` 标出继承、`auth`/`stoppable` 修饰器；`vars-and-auth` 标出 `isAuthorized(msg.sender,msg.sig)` 等条件 |

关键观察：

- **已能作为起点：** Slither 能编译两份真实源码，识别适配后的每个 `echidna_*` 属性，给出函数读写、内部调用、修饰器和 Echidna printer 的候选影响关系。它比仅扫描函数名或简单取读写集合提供更多上下文。
- **mapping 键未区分：** 读取 `balanceOf[0x10000]` 与 `balanceOf[address(0)]` 的两个属性获得完全一样的候选集合。对 `balanceOf[msg.sender]` 的写入也被列为可能影响零地址属性。这个结果适合作保守候选，不足以断言具体地址键相同或交易可达。
- **门控依赖未自动闭合：** DSToken 的候选列表包含 `mint`/`burn`，但没有把 `setOwner`、`setAuthority`、`stop`、`start` 加入两项属性的 `is_impacted_by`。`auth`、`stoppable`、`owner`、`authority.canCall` 可在其他 Slither 输出里观察到；下一步必须把权限、暂停状态、外部授权返回值与调用者关系另行关联。未解析的外部授权语义应标 `unknown`。
- **ETH 与外部执行语义仍缺失：** WETH9 的 `totalSupply()` 依赖 `address(this).balance`，`withdraw` 向 `msg.sender` 转 ETH。静态候选没有证明某笔交易的金额、余额或转账一定成功。

## 入口判断

对**原始源码**，答案是“尚不满足”：两份上游合约均没有已有显式安全属性，不能直接作为 V2 所定义的原生多属性样本。对**本次属性适配后的合约**，答案是“满足进入人工审查和属性上下文构建的最低结构条件”：编译成功，属性身份明确，可取得状态读写和候选函数。但尚不满足自动生成可执行交易种子的语义条件；mapping 键、权限、参数约束、ETH 环境和跨合约调用仍需补充分析及确定性执行验证。

这两份样本验证的是 Slither 接口在真实源码上的可用性，不能推断它对任意协议足够准确，也不能用于估计属性分组或 Agent 方法的收益。下一轮若选择原生多属性协议套件，应保留其完整编译依赖和原始属性，按相同入口条件重新检查。
