// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * Upstream source: OpenZeppelin Ethernaut Level 22 (Dex)
 * Repository: https://github.com/OpenZeppelin/ethernaut
 * License: MIT
 *
 * Self-contained single-file compilation of the original Dex & SwappableToken
 * business logic without external OpenZeppelin package dependencies, paired with
 * a standard reserve-solvency Echidna property.
 */

interface IERC20Like {
    function balanceOf(address account) external view returns (uint256);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

contract SwappableToken {
    string public name;
    string public symbol;
    uint8 public constant decimals = 18;
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
        require(balanceOf[msg.sender] >= amount, "ERC20: transfer amount exceeds balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        emit Transfer(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) public returns (bool) {
        require(balanceOf[from] >= amount, "ERC20: transfer amount exceeds balance");
        require(allowance[from][msg.sender] >= amount, "ERC20: insufficient allowance");
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
        return true;
    }
}

contract EthernautDexHarness {
    address public token1;
    address public token2;
    address public constant PLAYER = 0x0000000000000000000000000000000000010000;

    event Swapped(address indexed trader, address indexed from, address indexed to, uint256 amountIn, uint256 amountOut);

    constructor() {
        SwappableToken t1 = new SwappableToken(address(this), "Token 1", "TKN1", 110);
        SwappableToken t2 = new SwappableToken(address(this), "Token 2", "TKN2", 110);
        token1 = address(t1);
        token2 = address(t2);
        // Original Ethernaut Dex initial distribution: 100 each in DEX, 10 each to player
        t1.transfer(PLAYER, 10);
        t2.transfer(PLAYER, 10);
    }

    function swap(address from, address to, uint256 amount) public {
        require((from == token1 && to == token2) || (from == token2 && to == token1), "Invalid tokens");
        require(IERC20Like(from).balanceOf(msg.sender) >= amount, "Not enough to swap");
        uint256 swapAmount = getSwapPrice(from, to, amount);
        IERC20Like(from).transferFrom(msg.sender, address(this), amount);
        SwappableToken(to).approve(address(this), swapAmount);
        IERC20Like(to).transferFrom(address(this), msg.sender, swapAmount);
        emit Swapped(msg.sender, from, to, amount, swapAmount);
    }

    function getSwapPrice(address from, address to, uint256 amount) public view returns (uint256) {
        return ((amount * IERC20Like(to).balanceOf(address(this))) / IERC20Like(from).balanceOf(address(this)));
    }

    function approve(address spender, uint256 amount) public {
        SwappableToken(token1).approve(msg.sender, spender, amount);
        SwappableToken(token2).approve(msg.sender, spender, amount);
    }

    function balanceOf(address token, address account) public view returns (uint256) {
        return IERC20Like(token).balanceOf(account);
    }

    function dexBalance1() public view returns (uint256) {
        return IERC20Like(token1).balanceOf(address(this));
    }

    function dexBalance2() public view returns (uint256) {
        return IERC20Like(token2).balanceOf(address(this));
    }

    function playerBalance1() public view returns (uint256) {
        return IERC20Like(token1).balanceOf(PLAYER);
    }

    function playerBalance2() public view returns (uint256) {
        return IERC20Like(token2).balanceOf(PLAYER);
    }

    /// @notice Standard AMM reserve invariant: neither token reserve in the DEX should be drained to 0.
    function echidna_dex_reserves_non_empty() public view returns (bool) {
        return IERC20Like(token1).balanceOf(address(this)) > 0 &&
               IERC20Like(token2).balanceOf(address(this)) > 0;
    }
}
