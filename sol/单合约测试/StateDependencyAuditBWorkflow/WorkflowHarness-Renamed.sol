// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice Name-only semantic counterpart of WorkflowHarness.sol.
contract WorkOrderHarness {
    uint256 public phase;
    uint256 public quota;
    uint256 public appliedValue;

    function openOrder() external {
        require(phase == 0, "ORDER_ALREADY_OPEN");
        phase = 1;
    }

    function setQuota(uint256 ceiling) external {
        require(phase == 1, "ORDER_NOT_OPEN");
        require(ceiling > 0, "EMPTY_QUOTA");
        quota = ceiling;
        phase = 2;
    }

    function applyOrder(uint256 value) external {
        require(phase == 2, "ORDER_NOT_CONFIGURED");
        require(value > 0 && value <= quota, "QUOTA_EXCEEDED");
        appliedValue += value;
        phase = 3;
    }

    function echidna_order_value_within_quota() external view returns (bool) {
        return phase != 3 || appliedValue <= quota;
    }
}
