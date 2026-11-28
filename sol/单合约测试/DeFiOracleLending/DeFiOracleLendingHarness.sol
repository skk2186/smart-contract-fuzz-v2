// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * Representative DeFi Stateful Pattern: Spot-Price AMM Oracle Manipulation Against Lending Pool.
 * Modeled after Damn Vulnerable DeFi (Puppet) and real-world spot-price oracle exploits.
 *
 * Exploit chain:
 *   1. User swaps DebtToken into the small AMM pool to inflate the spot price of ColToken;
 *   2. User deposits minimal ColToken into the lending pool and borrows far more DebtToken
 *      than fair 1:1 value permits, draining the lending pool reserves.
 */
contract DeFiOracleLendingHarness {
    address public constant TRADER = 0x0000000000000000000000000000000000010000;

    // Constant-product AMM reserves (initial price 1:1)
    uint256 public ammColReserve = 1000;
    uint256 public ammDebtReserve = 1000;

    // Lending pool reserves & accounting
    uint256 public poolDebtReserve = 1000;
    mapping(address => uint256) public userColBalance;
    mapping(address => uint256) public userDebtBalance;
    mapping(address => uint256) public depositedCollateral;
    mapping(address => uint256) public borrowedDebt;
    bool public undercollateralizedBorrowObserved;

    event Swapped(address indexed user, bool debtToCol, uint256 amountIn, uint256 amountOut);
    event CollateralDeposited(address indexed user, uint256 amount);
    event Borrowed(address indexed user, uint256 debtAmount, uint256 spotPriceScaled);

    constructor() {
        userDebtBalance[TRADER] = 2000;
        userColBalance[TRADER] = 200;
    }

    /// @notice Vulnerable spot price scaled by 1e18 (debt per col).
    function getSpotPrice() public view returns (uint256) {
        return (ammDebtReserve * 1e18) / ammColReserve;
    }

    function swapDebtForCol(uint256 debtIn) external returns (uint256 colOut) {
        require(debtIn > 0 && userDebtBalance[msg.sender] >= debtIn, "INSUFFICIENT_DEBT");
        // x * y = k
        colOut = (debtIn * ammColReserve) / (ammDebtReserve + debtIn);
        require(colOut > 0 && colOut < ammColReserve, "BAD_SWAP");
        userDebtBalance[msg.sender] -= debtIn;
        ammDebtReserve += debtIn;
        ammColReserve -= colOut;
        userColBalance[msg.sender] += colOut;
        emit Swapped(msg.sender, true, debtIn, colOut);
    }

    function swapColForDebt(uint256 colIn) external returns (uint256 debtOut) {
        require(colIn > 0 && userColBalance[msg.sender] >= colIn, "INSUFFICIENT_COL");
        debtOut = (colIn * ammDebtReserve) / (ammColReserve + colIn);
        require(debtOut > 0 && debtOut < ammDebtReserve, "BAD_SWAP");
        userColBalance[msg.sender] -= colIn;
        ammColReserve += colIn;
        ammDebtReserve -= debtOut;
        userDebtBalance[msg.sender] += debtOut;
        emit Swapped(msg.sender, false, colIn, debtOut);
    }

    function depositCollateral(uint256 colAmount) external {
        require(colAmount > 0 && userColBalance[msg.sender] >= colAmount, "INSUFFICIENT_COL");
        userColBalance[msg.sender] -= colAmount;
        depositedCollateral[msg.sender] += colAmount;
        emit CollateralDeposited(msg.sender, colAmount);
    }

    function borrow(uint256 debtAmount) external {
        require(debtAmount > 0 && debtAmount <= poolDebtReserve, "POOL_LIQUIDITY_LOW");
        uint256 price = getSpotPrice();
        uint256 maxBorrow = (depositedCollateral[msg.sender] * price) / (2 * 1e18); // 200% collateral ratio
        require(borrowedDebt[msg.sender] + debtAmount <= maxBorrow, "INSUFFICIENT_COLLATERAL");

        borrowedDebt[msg.sender] += debtAmount;
        poolDebtReserve -= debtAmount;
        userDebtBalance[msg.sender] += debtAmount;

        // Under true 1:1 fair value, a 200% collateralized position must never borrow > depositedCollateral.
        if (borrowedDebt[msg.sender] > depositedCollateral[msg.sender] * 2) {
            undercollateralizedBorrowObserved = true;
        }
        emit Borrowed(msg.sender, debtAmount, price);
    }

    /// @notice Lending pool must never issue debt exceeding 2x fair 1:1 collateral value.
    function echidna_lending_pool_no_bad_debt() public view returns (bool) {
        return !undercollateralizedBorrowObserved;
    }
}
