// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// 仅用于验证静态接收者路径；不代表真实协议样本。
contract RegressionVault {
    uint256 public amount;
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "owner");
        _;
    }

    function setAmount(uint256 value) external onlyOwner {
        if (value > 10) {
            amount = value;
        } else {
            amount = value + 1;
        }
    }
}

contract RegressionHarness {
    RegressionVault public alpha;
    RegressionVault public beta;
    uint256 public localCounter;

    constructor() {
        alpha = new RegressionVault();
        beta = new RegressionVault();
    }

    function setAlpha(uint256 value) external {
        alpha.setAmount(value);
    }

    function setBeta(uint256 value) external {
        beta.setAmount(value);
    }

    function setLocal(uint256 value) external {
        if (value > 100) {
            localCounter = value;
        } else {
            localCounter = value + 1;
        }
    }

    function callDynamic(address target, bytes calldata data) external {
        (bool ok,) = target.call(data);
        require(ok, "call failed");
    }

    function echidna_alpha_bound() public view returns (bool) {
        return alpha.amount() <= 1000;
    }

    function echidna_beta_bound() public view returns (bool) {
        return beta.amount() <= 1000;
    }

    function echidna_local_bound() public view returns (bool) {
        return localCounter <= 1000;
    }
}
