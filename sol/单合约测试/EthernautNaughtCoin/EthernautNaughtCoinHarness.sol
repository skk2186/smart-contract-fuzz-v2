// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * Upstream source: OpenZeppelin Ethernaut Level 15 (Naught Coin)
 * Repository: https://github.com/OpenZeppelin/ethernaut
 * License: MIT
 *
 * Self-contained single-file reproduction of NaughtCoin without external OZ imports.
 * transfer() is locked for 10 years via lockTokens modifier, while transferFrom()
 * inherits standard ERC20 logic without the timelock modifier.
 */
contract EthernautNaughtCoinHarness {
    string public constant name = "NaughtCoin";
    string public constant symbol = "0x0";
    uint8 public constant decimals = 18;

    uint256 public timeLock;
    uint256 public INITIAL_SUPPLY;
    address public player;
    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    constructor() {
        player = 0x0000000000000000000000000000000000010000;
        timeLock = block.timestamp + 10 * 365 days;
        INITIAL_SUPPLY = 1000000 * (10 ** uint256(decimals));
        totalSupply = INITIAL_SUPPLY;
        balanceOf[player] = INITIAL_SUPPLY;
        emit Transfer(address(0), player, INITIAL_SUPPLY);
    }

    modifier lockTokens() {
        if (msg.sender == player) {
            require(block.timestamp > timeLock, "Tokens are time-locked");
        }
        _;
    }

    function transfer(address to, uint256 value) external lockTokens returns (bool) {
        require(to != address(0), "Zero recipient");
        require(balanceOf[msg.sender] >= value, "Insufficient balance");
        balanceOf[msg.sender] -= value;
        balanceOf[to] += value;
        emit Transfer(msg.sender, to, value);
        return true;
    }

    function approve(address spender, uint256 value) external returns (bool) {
        require(spender != address(0), "Zero spender");
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        require(to != address(0), "Zero recipient");
        require(balanceOf[from] >= value, "Insufficient balance");
        require(allowance[from][msg.sender] >= value, "Insufficient allowance");
        allowance[from][msg.sender] -= value;
        balanceOf[from] -= value;
        balanceOf[to] += value;
        emit Transfer(from, to, value);
        return true;
    }

    /// @notice Original Ethernaut win condition inverted: player must not drain full locked balance during lockup.
    function echidna_locked_balance_not_drained() public view returns (bool) {
        if (block.timestamp <= timeLock) {
            return balanceOf[player] > 0;
        }
        return true;
    }
}
