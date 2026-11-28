// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * Upstream source: OpenZeppelin Ethernaut Level 23 (Dex Two)
 * Repository: https://github.com/OpenZeppelin/ethernaut
 * License: MIT
 *
 * Self-contained single-file reproduction of DexTwo where swap() omits the
 * token1/token2 allowlist check, enabling an arbitrary third ERC20 token
 * (mockToken) to drain BOTH token1 and token2 reserves from the DEX.
 */
interface IERC20Dex2 {
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

contract SwappableTokenTwo {
    string public name;
    string public symbol;
    uint256 public totalSupply;
    address private _dex;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    constructor(address dexInstance, string memory name_, string memory symbol_, uint256 initialSupply) {
        _dex = dexInstance;
        name = name_;
        symbol = symbol_;
        totalSupply = initialSupply;
        balanceOf[msg.sender] = initialSupply;
        emit Transfer(address(0), msg.sender, initialSupply);
    }

    function approve(address spender, uint256 amount) public returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function approve(address owner, address spender, uint256 amount) public {
        require(owner != _dex, "InvalidApprover");
        allowance[owner][spender] = amount;
        emit Approval(owner, spender, amount);
    }

    function transfer(address to, uint256 amount) public returns (bool) {
        require(balanceOf[msg.sender] >= amount, "ERC20: balance too low");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        emit Transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) public returns (bool) {
        require(balanceOf[from] >= amount, "ERC20: balance too low");
        require(allowance[from][msg.sender] >= amount, "ERC20: insufficient allowance");
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
        return true;
    }
}

contract EthernautDexTwoHarness {
    address public token1;
    address public token2;
    address public sideToken;
    address public constant PLAYER = 0x0000000000000000000000000000000000010000;

    event Swapped(address indexed trader, address indexed from, address indexed to, uint256 amountIn, uint256 amountOut);

    constructor() {
        SwappableTokenTwo t1 = new SwappableTokenTwo(address(this), "Token 1", "TKN1", 110);
        SwappableTokenTwo t2 = new SwappableTokenTwo(address(this), "Token 2", "TKN2", 110);
        SwappableTokenTwo st = new SwappableTokenTwo(address(this), "Side Token", "SIDE", 400);
        token1 = address(t1);
        token2 = address(t2);
        sideToken = address(st);
        t1.transfer(PLAYER, 10);
        t2.transfer(PLAYER, 10);
        // Side token belongs entirely to PLAYER (equivalent to user deploying a mock ERC20 in Ethernaut)
        st.transfer(PLAYER, 400);
    }

    function swap(address from, address to, uint256 amount) public {
        require(IERC20Dex2(from).balanceOf(msg.sender) >= amount, "Not enough to swap");
        uint256 swapAmount = getSwapAmount(from, to, amount);
        IERC20Dex2(from).transferFrom(msg.sender, address(this), amount);
        SwappableTokenTwo(to).approve(address(this), swapAmount);
        IERC20Dex2(to).transferFrom(address(this), msg.sender, swapAmount);
        emit Swapped(msg.sender, from, to, amount, swapAmount);
    }

    function getSwapAmount(address from, address to, uint256 amount) public view returns (uint256) {
        return ((amount * IERC20Dex2(to).balanceOf(address(this))) / IERC20Dex2(from).balanceOf(address(this)));
    }

    function approve(address spender, uint256 amount) public {
        SwappableTokenTwo(token1).approve(msg.sender, spender, amount);
        SwappableTokenTwo(token2).approve(msg.sender, spender, amount);
        SwappableTokenTwo(sideToken).approve(msg.sender, spender, amount);
    }

    function transferSideTokenToDex(uint256 amount) public {
        SwappableTokenTwo(sideToken).transferFrom(msg.sender, address(this), amount);
    }

    function dexBalance1() public view returns (uint256) {
        return IERC20Dex2(token1).balanceOf(address(this));
    }

    function dexBalance2() public view returns (uint256) {
        return IERC20Dex2(token2).balanceOf(address(this));
    }

    function dexSideBalance() public view returns (uint256) {
        return IERC20Dex2(sideToken).balanceOf(address(this));
    }

    function playerSideBalance() public view returns (uint256) {
        return IERC20Dex2(sideToken).balanceOf(PLAYER);
    }

    /// @notice Original Ethernaut DexTwo win condition inverted: at least one reserve must remain non-zero.
    function echidna_both_reserves_not_drained() public view returns (bool) {
        return IERC20Dex2(token1).balanceOf(address(this)) > 0 ||
               IERC20Dex2(token2).balanceOf(address(this)) > 0;
    }
}
