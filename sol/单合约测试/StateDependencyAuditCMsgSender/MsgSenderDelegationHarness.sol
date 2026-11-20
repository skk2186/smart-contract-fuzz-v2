// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice Caller identity is exclusively msg.sender; no integer actor selector exists.
contract MsgSenderDelegationHarness {
    address public constant TARGET_OWNER = 0x0000000000000000000000000000000000010000;
    address public constant TARGET_OPERATOR = 0x0000000000000000000000000000000000020000;

    mapping(address => uint256) public depositedCredit;
    mapping(address => uint256) public availableCredit;
    mapping(address => address) public authorizedOperator;
    mapping(address => uint256) public executedFor;

    function fundCredit() external payable {
        require(msg.value > 0, "EMPTY_FUNDING");
        depositedCredit[msg.sender] += msg.value;
        availableCredit[msg.sender] += msg.value;
    }

    function authorizeOperator(address operator) external {
        require(operator != address(0), "ZERO_OPERATOR");
        authorizedOperator[msg.sender] = operator;
    }

    function executeFor(address owner, uint256 amount) external {
        require(authorizedOperator[owner] == msg.sender, "NOT_AUTHORIZED_OPERATOR");
        require(amount > 0 && availableCredit[owner] >= amount, "INSUFFICIENT_CREDIT");
        availableCredit[owner] -= amount;
        executedFor[owner] += amount;
    }

    function echidna_delegated_execution_is_bounded() external view returns (bool) {
        return executedFor[TARGET_OWNER] <= depositedCredit[TARGET_OWNER] &&
            (executedFor[TARGET_OWNER] == 0 ||
             authorizedOperator[TARGET_OWNER] == TARGET_OPERATOR);
    }
}
