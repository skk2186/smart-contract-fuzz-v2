// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice ERC20-like balance/allowance state used to audit non-ETH dependencies.
contract AllowanceHarness {
    address public constant TARGET_OWNER = 0x0000000000000000000000000000000000010000;
    address public constant TARGET_SPENDER = 0x0000000000000000000000000000000000020000;
    address public constant TARGET_RECIPIENT = 0x0000000000000000000000000000000000030000;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    mapping(address => mapping(address => uint256)) public totalGranted;
    mapping(address => mapping(address => uint256)) public delegatedSpent;
    uint256 public totalSupply;

    function mint(address recipient, uint256 amount) external {
        require(recipient != address(0) && amount > 0, "BAD_MINT");
        balanceOf[recipient] += amount;
        totalSupply += amount;
    }

    function approve(address spender, uint256 amount) external {
        require(spender != address(0), "ZERO_SPENDER");
        allowance[msg.sender][spender] = amount;
        totalGranted[msg.sender][spender] += amount;
    }

    function transferFrom(address owner, address recipient, uint256 amount) external {
        require(amount > 0, "EMPTY_TRANSFER");
        require(allowance[owner][msg.sender] >= amount, "ALLOWANCE_TOO_LOW");
        require(balanceOf[owner] >= amount, "BALANCE_TOO_LOW");
        allowance[owner][msg.sender] -= amount;
        balanceOf[owner] -= amount;
        balanceOf[recipient] += amount;
        delegatedSpent[owner][msg.sender] += amount;
    }

    function echidna_delegated_spend_is_bounded() external view returns (bool) {
        return delegatedSpent[TARGET_OWNER][TARGET_SPENDER] <=
                totalGranted[TARGET_OWNER][TARGET_SPENDER] &&
            balanceOf[TARGET_OWNER] + balanceOf[TARGET_SPENDER] <= totalSupply;
    }
}
