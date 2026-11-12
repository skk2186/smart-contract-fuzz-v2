// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../KinkPool.sol";
import "../KinkFactory.sol";
import "../PoolRegistry.sol";
import "../mocks/MockERC20.sol";
import "../mocks/FeeOnTransferToken.sol";

contract KinkPoolEchidna {
    KinkPool public pool;
    FeeOnTransferToken public token0;
    MockERC20 public token1;

    uint256 public immutable initialToken0;
    uint256 public immutable initialToken1;

    uint256 private constant SEED_AMOUNT = 10_000e18;
    uint256 private constant MAX_SINGLE_SWAP = 100_000e18;

    constructor() {
        token0 = new FeeOnTransferToken("Fee Token", "FEE", 100); // 1% burn
        token1 = new MockERC20("Token1", "T1");

        PoolRegistry registry = new PoolRegistry(address(this), address(0));
        KinkFactory factory = new KinkFactory(address(registry));
        registry.setFactory(address(factory));
        address poolAddress = factory.createPool(address(token0), address(token1), 100, 200, 4, 10, 2e18, 2e18);
        pool = KinkPool(poolAddress);

        token0.approve(poolAddress, type(uint256).max);
        token1.approve(poolAddress, type(uint256).max);

        initialToken0 = token0.balanceOf(address(this));
        initialToken1 = token1.balanceOf(address(this));

        _provideSeedLiquidity();
    }

    // ======== Fuzz entrypoints ========

    function adversarialSwap(uint256 rawDx, uint256 direction) external {
        if (pool.totalSupply() == 0) return;
        uint256 side = direction % 2;
        if (side == 0) {
            uint256 dx = _bound(rawDx, _min(token0.balanceOf(address(this)), MAX_SINGLE_SWAP));
            if (dx == 0) return;
            pool.exchange(0, 1, dx, 0);
        } else {
            uint256 dx = _bound(rawDx, _min(token1.balanceOf(address(this)), MAX_SINGLE_SWAP));
            if (dx == 0) return;
            pool.exchange(1, 0, dx, 0);
        }
    }

    function singleSidedAdd(uint256 rawAmount, uint256 side) external {
        uint256 index = side % 2;
        uint256[2] memory amounts;
        if (index == 0) {
            uint256 amount = _bound(rawAmount, token0.balanceOf(address(this)));
            if (amount == 0) return;
            amounts[0] = amount;
        } else {
            uint256 amount = _bound(rawAmount, token1.balanceOf(address(this)));
            if (amount == 0) return;
            amounts[1] = amount;
        }
        pool.add_liquidity(amounts, 0);
    }

    function yankLiquidity(uint256 rawLp) external {
        uint256 lpBalance = pool.balanceOf(address(this));
        if (lpBalance == 0) return;
        uint256 amount = _bound(rawLp, lpBalance);
        if (amount == 0) return;
        uint256[2] memory mins;
        pool.remove_liquidity(amount, mins);
    }

    // ======== Properties ========

    function echidna_token0_accounting() external view returns (bool) {
        uint256 accounted = token0.balanceOf(address(this)) + token0.balanceOf(address(pool)) + token0.totalBurned();
        return accounted == initialToken0;
    }

    function echidna_token1_conserved() external view returns (bool) {
        return token1.balanceOf(address(this)) + token1.balanceOf(address(pool)) == initialToken1;
    }

    function echidna_reserves_match_balances() external view returns (bool) {
        (uint256 reserve0, uint256 reserve1) = pool.getReserves();
        return reserve0 == token0.balanceOf(address(pool)) && reserve1 == token1.balanceOf(address(pool));
    }

    function echidna_invariant_matches_supply() external view returns (bool) {
        uint256 supply = pool.totalSupply();
        uint256 invariantValue = pool.currentInvariant();
        if (supply == 0) {
            return invariantValue == 0
                && token0.balanceOf(address(pool)) == 0
                && token1.balanceOf(address(pool)) == 0;
        }
        if (supply >= invariantValue) {
            return supply - invariantValue <= 1;
        }
        return invariantValue - supply <= 1;
    }

    // ======== Helpers ========

    function _provideSeedLiquidity() internal {
        uint256[2] memory seedAmounts;
        seedAmounts[0] = SEED_AMOUNT;
        seedAmounts[1] = SEED_AMOUNT;
        pool.add_liquidity(seedAmounts, 0);
    }

    function _bound(uint256 raw, uint256 max) internal pure returns (uint256) {
        if (max == 0) return 0;
        return raw % (max + 1);
    }

    function _min(uint256 a, uint256 b) internal pure returns (uint256) {
        return a < b ? a : b;
    }
}


