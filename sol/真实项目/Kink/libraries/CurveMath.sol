// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title CurveMath
 * @notice Stableswap math library ported from Curve Fi's StableSwap.vy
 * @dev Implements the Stableswap invariant with dynamic amplification parameter A
 */
library CurveMath {
    uint256 public constant A_PRECISION = 100;
    uint256 public constant N_COINS = 2;
    uint256 public constant PRECISION = 1e18;

    /**
     * @notice Calculate D (invariant) using Newton-Raphson method
     * @param xp Normalized balances array
     * @param A Amplification parameter
     * @return D The invariant value, or 0 if convergence fails
     */
    function get_D(uint256[N_COINS] memory xp, uint256 A) internal pure returns (uint256) {
        uint256 S = 0;
        for (uint256 i = 0; i < N_COINS; i++) {
            S += xp[i];
        }
        if (S == 0) {
            return 0;
        }

        uint256 D = S;
        uint256 Ann = A * N_COINS;

        for (uint256 i = 0; i < 255; i++) {
            uint256 D_P = D;
            for (uint256 j = 0; j < N_COINS; j++) {
                D_P = (D_P * D) / (xp[j] * N_COINS + 1); // +1 to prevent /0
            }
            uint256 D_prev = D;
            D = ((Ann * S + D_P * N_COINS) * D) / ((Ann - 1) * D + (N_COINS + 1) * D_P);

            // Equality with the precision of 1
            if (D > D_prev) {
                if (D - D_prev <= 1) {
                    return D;
                }
            } else {
                if (D_prev - D <= 1) {
                    return D;
                }
            }
        }

        // Convergence failed, return 0
        return 0;
    }

    /**
     * @notice Calculate y (output amount) when x (input amount) changes
     * @param i Index of input token
     * @param j Index of output token
     * @param x New balance of input token
     * @param xp Current normalized balances
     * @param A Amplification parameter
     * @return y Output amount
     */
    function get_y(uint256 i, uint256 j, uint256 x, uint256[N_COINS] memory xp, uint256 A)
        internal
        pure
        returns (uint256)
    {
        require(i != j && i < N_COINS && j < N_COINS, "CurveMath: Invalid indices");

        uint256 D = get_D(xp, A);
        uint256 c = D;
        uint256 S_ = 0;
        uint256 Ann = A * N_COINS;

        uint256 _x = 0;
        for (uint256 _i = 0; _i < N_COINS; _i++) {
            if (_i == i) {
                _x = x;
            } else if (_i != j) {
                _x = xp[_i];
            } else {
                continue;
            }
            S_ += _x;
            c = (c * D) / (_x * N_COINS);
        }
        c = (c * D) / (Ann * N_COINS);
        uint256 b = S_ + D / Ann;
        uint256 y_prev = 0;
        uint256 y = D;

        for (uint256 _i = 0; _i < 255; _i++) {
            y_prev = y;
            y = (y * y + c) / (2 * y + b - D);
            if (y > y_prev) {
                if (y - y_prev <= 1) {
                    return y;
                }
            } else {
                if (y_prev - y <= 1) {
                    return y;
                }
            }
        }

        // If convergence fails, return 0
        return 0;
    }

    /**
     * @notice Calculate y given D
     * @param A Amplification parameter
     * @param i Index of token to calculate
     * @param xp Current normalized balances
     * @param D The invariant D
     * @return y Output amount
     */
    function get_y_D(uint256 A, uint256 i, uint256[N_COINS] memory xp, uint256 D) internal pure returns (uint256) {
        require(i < N_COINS, "CurveMath: Invalid index");

        uint256 c = D;
        uint256 S_ = 0;
        uint256 Ann = A * N_COINS;

        uint256 _x = 0;
        for (uint256 _i = 0; _i < N_COINS; _i++) {
            if (_i != i) {
                _x = xp[_i];
            } else {
                continue;
            }
            S_ += _x;
            c = (c * D) / (_x * N_COINS);
        }
        c = (c * D) / (Ann * N_COINS);
        uint256 b = S_ + D / Ann;
        uint256 y_prev = 0;
        uint256 y = D;

        for (uint256 _i = 0; _i < 255; _i++) {
            y_prev = y;
            y = (y * y + c) / (2 * y + b - D);
            if (y > y_prev) {
                if (y - y_prev <= 1) {
                    return y;
                }
            } else {
                if (y_prev - y <= 1) {
                    return y;
                }
            }
        }

        return 0;
    }
}
