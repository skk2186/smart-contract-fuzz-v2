// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice Minimal audit fixture for persistent create/configure/execute state.
contract WorkflowHarness {
    uint256 public stage;
    uint256 public executionLimit;
    uint256 public completedAmount;

    function createTask() external {
        require(stage == 0, "ALREADY_CREATED");
        stage = 1;
    }

    function configureTask(uint256 maxAmount) external {
        require(stage == 1, "TASK_NOT_CREATED");
        require(maxAmount > 0, "EMPTY_LIMIT");
        executionLimit = maxAmount;
        stage = 2;
    }

    function executeTask(uint256 amount) external {
        require(stage == 2, "TASK_NOT_CONFIGURED");
        require(amount > 0 && amount <= executionLimit, "LIMIT_EXCEEDED");
        completedAmount += amount;
        stage = 3;
    }

    function echidna_workflow_respects_limit() external view returns (bool) {
        return stage != 3 || completedAmount <= executionLimit;
    }
}
