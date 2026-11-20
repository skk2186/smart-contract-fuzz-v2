# Phase32-R 兼容 Harness

Properties.sol 是 Pigfox 上游 test/Properties.sol 的隔离副本。唯一改动是将 TOKEN 和 holders 两个 internal 状态引用改为 public，使属性实际读取的 RWAToken.totalSupply() 与 RWAToken.balanceOf(holder) 可由外部只读 ABI 观察。只读 getter 不提供状态写入入口，不改变构造、动作和属性函数实现。

业务合约、Actor 与 PigfoxProperties 均通过临时运行目录的符号链接引用上游文件；上游源码不修改。该副本使用 CryticCompile 0.4.2 和 solc 0.8.28 直接编译，不经过 Foundry 生成的 DeployHelper/HEVM::deployCode 路径。E0/E1/E3 必须共用这份 Harness。
