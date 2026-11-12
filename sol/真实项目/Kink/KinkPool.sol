// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/token/ERC20/extensions/IERC20Metadata.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/proxy/utils/Initializable.sol";

import "./libraries/CurveMath.sol";

interface IKinkFactory {
    function feeReceiver() external view returns (address);
    function baseFeeShare() external view returns (uint256);
    function kinkingFeeShare() external view returns (uint256);
}

/**
 * @title KinkPool
 * @notice Two-asset stableswap pool with asymmetric amplification ("kink") behavior.
 *         Deploy through `KinkFactory` which clones this implementation and calls `initialize`.
 */
contract KinkPool is ERC20, ReentrancyGuard, Initializable {
    using SafeERC20 for IERC20;

    uint256 private constant N_COINS = 2;
    uint256 public constant FEE_DENOMINATOR = 10_000;
    uint256 public constant MINIMUM_LIQUIDITY = 1000;

    address public factory;
    address public admin;
    address public pendingAdmin; // Governance fix: Two-step transfer
    address public token0;
    address public token1;
    uint8 public token0Decimals;
    uint8 public token1Decimals;
    uint256 public A0;
    uint256 public A1;
    uint256 public baseFee;
    uint256 public kinkingFee;
    uint256 public softPeg0;
    uint256 public softPeg1;
    uint256[N_COINS] private tokenMultipliers;

    event Exchange(
        address indexed buyer,
        address indexed receiver,
        uint256 i,
        uint256 j,
        uint256 dx,
        uint256 dy
    );

    event AdminChanged(address indexed oldAdmin, address indexed newAdmin);
    event OwnershipTransferStarted(address indexed previousOwner, address indexed newOwner);
    event AdminFeesCollected(uint256 amount0, uint256 amount1);

    modifier onlyAdmin() {
        require(msg.sender == admin, "KinkPool: Only admin");
        _;
    }

    event AddLiquidity(
        address indexed provider,
        uint256[N_COINS] amounts,
        uint256 lpAmount
    );

    event RemoveLiquidity(
        address indexed provider,
        uint256[N_COINS] amounts,
        uint256 lpAmount
    );

    constructor() ERC20("Kink Pool LP", "KINK-LP") {
        // Disable initialization of implementation contract
        _disableInitializers();
    }

    /**
     * @notice Initialize the pool
     * @param _token0 Address of token0
     * @param _token1 Address of token1
     * @param _A0 Amplification parameter when token0 > token1
     * @param _A1 Amplification parameter when token1 > token0
     * @param _baseFee Base fee in basis points (for converging trades)
     * @param _kinkingFee Kinking fee in basis points (for diverging trades)
     */
    function initialize(
        address _token0,
        address _token1,
        uint256 _A0,
        uint256 _A1,
        uint256 _baseFee,
        uint256 _kinkingFee,
        uint256 _softPeg0,
        uint256 _softPeg1,
        address _admin
    ) external initializer {
        require(_token0 != address(0) && _token1 != address(0), "KinkPool: Zero address");
        require(_token0 < _token1, "KinkPool: Tokens not sorted");
        require(_A0 >= 2 && _A0 <= 1000, "KinkPool: Invalid A0");
        require(_A1 >= 2 && _A1 <= 1000, "KinkPool: Invalid A1");
        require(_baseFee <= FEE_DENOMINATOR, "KinkPool: Invalid baseFee");
        require(_kinkingFee <= FEE_DENOMINATOR, "KinkPool: Invalid kinkingFee");
        // _softPeg0 and _softPeg1 are typically around 1e18 (1.0).

        uint8 decimals0 = IERC20Metadata(_token0).decimals();
        uint8 decimals1 = IERC20Metadata(_token1).decimals();
        require(decimals0 <= 18 && decimals1 <= 18, "KinkPool: Decimals too large");
        // decimals mismatch requirement removed

        factory = msg.sender;
        admin = _admin;
        token0 = _token0;
        token1 = _token1;
        token0Decimals = decimals0;
        token1Decimals = decimals1;
        A0 = _A0;
        A1 = _A1;
        baseFee = _baseFee;
        kinkingFee = _kinkingFee;
        softPeg0 = _softPeg0;
        softPeg1 = _softPeg1;

        tokenMultipliers[0] = 10 ** (18 - decimals0);
        tokenMultipliers[1] = 10 ** (18 - decimals1);
    }

    /**
     * @notice Start ownership transfer
     * @param newOwner New admin address
     */
    function transferOwnership(address newOwner) external onlyAdmin {
        require(newOwner != address(0), "KinkPool: Zero address");
        pendingAdmin = newOwner;
        emit OwnershipTransferStarted(admin, newOwner);
    }

    /**
     * @notice Collect accumulated admin fees
     */
    uint256 public adminFee0;
    uint256 public adminFee1;

    function collectFees() external nonReentrant {
        address feeReceiver = IKinkFactory(factory).feeReceiver();
        require(feeReceiver != address(0), "KinkPool: Fee receiver not set");

        uint256 amount0 = adminFee0;
        uint256 amount1 = adminFee1;

        if (amount0 > 0) {
            adminFee0 = 0;
            IERC20(token0).safeTransfer(feeReceiver, amount0);
        }
        if (amount1 > 0) {
            adminFee1 = 0;
            IERC20(token1).safeTransfer(feeReceiver, amount1);
        }

        emit AdminFeesCollected(amount0, amount1);
    }

    function _balances() internal view returns (uint256[N_COINS] memory reserves) {
        reserves[0] = IERC20(token0).balanceOf(address(this)) - adminFee0;
        reserves[1] = IERC20(token1).balanceOf(address(this)) - adminFee1;
    }

    /**
     * @notice Normalize balances to 18 decimals using stored multipliers
     * @param balances Raw balance array
     * @return xp Normalized balances array
     */
    function _xp(uint256[N_COINS] memory balances) internal view returns (uint256[N_COINS] memory xp) {
        xp[0] = balances[0] * tokenMultipliers[0];
        xp[1] = balances[1] * tokenMultipliers[1];
    }

    /**
     * @notice Get current amplification parameter based on balances
     */
    function _get_current_A() internal view returns (uint256) {
        uint256[N_COINS] memory xp = _xp(_balances());
        return _get_A(xp);
    }

    /**
     * @notice Get amplification parameter based on explicit balances
     */
    function _get_A(uint256[N_COINS] memory xp) internal view returns (uint256) {
        if (xp[0] > xp[1]) {
            return A0;
        } else {
            return A1;
        }
    }

    /**
     * @notice Expose current amplification parameter for external observers
     */
    function currentAmplification() external view returns (uint256) {
        return _get_current_A();
    }

    /**
     * @notice Get current normalized balances (18 decimals)
     */
    function getNormalizedReserves() external view returns (uint256[N_COINS] memory xp) {
        return _xp(_balances());
    }

    /**
     * @notice Get current StableSwap invariant D
     */
    function currentInvariant() external view returns (uint256) {
        uint256[N_COINS] memory xp = _xp(_balances());
        return CurveMath.get_D(xp, _get_current_A());
    }

    /**
     * @notice Calculate virtual marginal price using small epsilon
     * @param i Index of input token
     * @param j Index of output token
     * @param x Input balance (normalized)
     * @param xp Current normalized balances
     * @param A Amplification parameter
     * @return Price in 18 decimals (output token per input token)
     */
    function _get_marginal_price(
        uint256 i,
        uint256 j,
        uint256 x,
        uint256[N_COINS] memory xp,
        uint256 A
    ) internal pure returns (uint256) {
        // Simulate price by checking y at x and x+epsilon
        uint256 epsilon = 1e15; // 0.001 unit (normalized 18 decimals)

        uint256 y1 = CurveMath.get_y(i, j, x, xp, A);
        uint256 y2 = CurveMath.get_y(i, j, x + epsilon, xp, A);

        if (y1 <= y2) return 0; // Should not happen

        // dy = y1 - y2
        // dx = epsilon
        // price = dy/dx
        return ((y1 - y2) * 1e18) / epsilon;
    }

    /**
     * @notice Binary search to find dx where price crosses peg
     */
    function _find_crossing_dx(
        uint256 i,
        uint256 j,
        uint256 startX,
        uint256[N_COINS] memory xp,
        uint256 A,
        uint256 peg,
        uint256 maxDx
    ) internal pure returns (uint256) {
        uint256 low = 0;
        uint256 high = maxDx;

        // 10 iterations provides decent precision for this purpose
        // Note: Minor precision loss on fee splitting is acceptable / expected behavior.
        for (uint256 k = 0; k < 10; k++) {
            uint256 mid = (low + high) / 2;
            if (mid == 0) {
                low = 1;
                continue;
            }
            uint256 price = _get_marginal_price(i, j, startX + mid, xp, A);

            if (price > peg) {
                // Price too high, need more dx (price drops as x increases)
                low = mid;
            } else {
                // Price too low, need less dx
                high = mid;
            }
        }
        return (low + high) / 2;
    }

    function _calculate_exchange(
        uint256 i,
        uint256 j,
        uint256 actualDx,
        uint256[N_COINS] memory xpBefore
    ) internal view returns (uint256 dy, uint256 adminFeeAmount) {
        uint256 baseFeeShare = IKinkFactory(factory).baseFeeShare();
        uint256 kinkingFeeShare = IKinkFactory(factory).kinkingFeeShare();

        uint256 currentA = xpBefore[0] > xpBefore[1] ? A0 : A1;
        // Determine if current A is correct. The logic in _get_A matches this.
        // A is based on the current state balances.

        uint256 D = CurveMath.get_D(xpBefore, currentA);
        uint256 thresholdXP = D / N_COINS;

        // Check if swap crosses equilibrium (1:1 point)
        bool crossesEquilibrium = false;
        uint256 dx1 = 0;
        uint256 dx2 = 0;

        if (xpBefore[i] < xpBefore[j]) {
            // Currently converging (xp[i] < xp[j])
            // Check if we cross the threshold (D/2)
            uint256 dxNormalized = actualDx * tokenMultipliers[i];
            if (xpBefore[i] + dxNormalized > thresholdXP) {
                // Check if we actually cross (avoid precision issues if very close)
                // If xpBefore[i] + dxNormalized > thresholdXP, we MIGHT cross.
                // The gap to reach D/2 is (thresholdXP - xpBefore[i]).
                uint256 gapNormalized = thresholdXP - xpBefore[i];

                // dx1 is the input required to reach equilibrium
                // Since input is added to pool, increasing x, we just fill the gap to D/2.
                // Note: this is an approximation for the split point because D is invariant.

                uint256 gapDx = gapNormalized / tokenMultipliers[i];
                if (gapDx < actualDx) {
                    crossesEquilibrium = true;
                    dx1 = gapDx;
                    dx2 = actualDx - gapDx;
                }
            }
        }

        if (crossesEquilibrium) {
            // Split swap: first part converges (baseFee), second part diverges (kinkingFee)
            // First part: swap dx1
            uint256[N_COINS] memory xp1 = xpBefore;
            uint256 dx1Normalized = dx1 * tokenMultipliers[i];
            uint256 x1 = xp1[i] + dx1Normalized;
            uint256 y1 = CurveMath.get_y(i, j, x1, xp1, currentA);
            require(y1 > 0, "KinkPool: Convergence failed"); // Fix #2
            uint256 dy1Normalized = xp1[j] - y1;

            // Apply baseFee to the converging part
            uint256 dy1FeeTotal = (dy1Normalized * baseFee) / FEE_DENOMINATOR;

            // Calculate admin share
            uint256 adminShare1 = (dy1FeeTotal * baseFeeShare) / FEE_DENOMINATOR;
            // Denormalize admin share to token units
            if (adminShare1 > 0) {
                adminFeeAmount += adminShare1 / tokenMultipliers[j];
            }

            dy1Normalized -= dy1FeeTotal;

            uint256 dy1 = dy1Normalized / tokenMultipliers[j];

            // Update balances to reflect first swap outcome
            xp1[i] = x1;
            xp1[j] = xpBefore[j] - dy1Normalized - adminShare1;

            // Second swap with target A (opposite side)
            uint256 targetA = i == 0 ? A0 : A1; // Fix #3: i=0 means token0 input, so we become token0 heavy -> A0
            uint256[N_COINS] memory xp2 = xp1;
            uint256 dx2Normalized = dx2 * tokenMultipliers[i];
            uint256 x2 = xp2[i] + dx2Normalized;
            uint256 y2 = CurveMath.get_y(i, j, x2, xp2, targetA);
            require(y2 > 0, "KinkPool: Convergence failed"); // Fix #2
            uint256 dy2Normalized = xp2[j] - y2;

            // Apply fee to the diverging part based on soft peg logic
            // The diverging part starts at equilibrium (price ~ 1.0).
            // If softPeg < 1.0, we start in the "good" zone (price > softPeg).
            // We check if the swap pushes price below softPeg.

            uint256 peg = i == 0 ? softPeg0 : softPeg1;
            uint256 fee = baseFee;

            if (dx2Normalized > 0) {
                // Check marginal price at the end of the swap
                // x2 is the end state of input token balance
                uint256 endPrice = _get_marginal_price(i, j, x2, xp2, targetA);

                if (endPrice < peg) {
                    // We crossed the peg.
                    // We assume we started above peg (since we started at equilibrium ~1.0).
                    // Find the split point.
                    uint256 startPrice = _get_marginal_price(i, j, xp2[i], xp2, targetA);

                    if (startPrice > peg) {
                        // Fix #2: Use binary search instead of linear interpolation
                        uint256 dxSplitNormalized = _find_crossing_dx(i, j, xp2[i], xp2, targetA, peg, dx2Normalized);

                        // Safety check
                        if (dxSplitNormalized > dx2Normalized) dxSplitNormalized = dx2Normalized;

                        // Split calculations
                        // 1. Base fee part
                        uint256 xSplit = xp2[i] + dxSplitNormalized;
                        uint256 ySplit = CurveMath.get_y(i, j, xSplit, xp2, targetA);
                        uint256 dySplitNormalized = xp2[j] - ySplit;

                        // 2. Kinking fee part (remaining)
                        // Total dy (dy2Normalized) is already calculated as xp2[j] - y2.
                        // Remaining dy = dy2Normalized - dySplitNormalized
                        uint256 dyRestNormalized = dy2Normalized - dySplitNormalized;

                        // Apply fees
                        uint256 feeBasePart = (dySplitNormalized * baseFee) / FEE_DENOMINATOR;
                        uint256 feeKinkPart = (dyRestNormalized * kinkingFee) / FEE_DENOMINATOR;
                        uint256 totalFee = feeBasePart + feeKinkPart;

                        // Admin share
                        uint256 adminShareBase = (feeBasePart * baseFeeShare) / FEE_DENOMINATOR;
                        uint256 adminShareKink = (feeKinkPart * kinkingFeeShare) / FEE_DENOMINATOR;
                        uint256 totalAdminShare = adminShareBase + adminShareKink;

                        if (totalAdminShare > 0) {
                            adminFeeAmount += totalAdminShare / tokenMultipliers[j];
                        }

                        dy2Normalized -= totalFee;

                    } else {
                        // Started below peg? (Unlikely for diverging from equilibrium, but possible if peg > 1.0)
                        fee = kinkingFee;
                        uint256 dy2FeeTotal = (dy2Normalized * fee) / FEE_DENOMINATOR;
                        uint256 adminShare2 = (dy2FeeTotal * kinkingFeeShare) / FEE_DENOMINATOR;
                         if (adminShare2 > 0) {
                            adminFeeAmount += adminShare2 / tokenMultipliers[j];
                        }
                        dy2Normalized -= dy2FeeTotal;
                    }
                } else {
                    // End price >= peg. Whole swap is base fee.
                    uint256 dy2FeeTotal = (dy2Normalized * baseFee) / FEE_DENOMINATOR;
                    uint256 adminShare2 = (dy2FeeTotal * baseFeeShare) / FEE_DENOMINATOR;
                    if (adminShare2 > 0) {
                        adminFeeAmount += adminShare2 / tokenMultipliers[j];
                    }
                    dy2Normalized -= dy2FeeTotal;
                }
            }

            uint256 dy2 = dy2Normalized / tokenMultipliers[j];
            dy = dy1 + dy2;
        } else {
            // Standard swap
            bool converging = false;
            if (xpBefore[i] < xpBefore[j]) {
                converging = true;
            }

            uint256 dxNormalized = actualDx * tokenMultipliers[i];
            uint256 x = xpBefore[i] + dxNormalized;
            uint256 y = CurveMath.get_y(i, j, x, xpBefore, currentA);
            require(y > 0, "KinkPool: Convergence failed"); // Fix #2
            uint256 dyNormalized = xpBefore[j] - y;

            if (!converging) {
                 uint256 peg = i == 0 ? softPeg0 : softPeg1;
                 uint256 fee = baseFee;

                 if (dxNormalized > 0) {
                    uint256 endPrice = _get_marginal_price(i, j, x, xpBefore, currentA);

                    if (endPrice < peg) {
                        // Check start price
                        uint256 startPrice = _get_marginal_price(i, j, xpBefore[i], xpBefore, currentA);

                        if (startPrice > peg) {
                            // Fix #2: Use binary search instead of linear interpolation
                            uint256 dxSplitNormalized = _find_crossing_dx(i, j, xpBefore[i], xpBefore, currentA, peg, dxNormalized);

                            // Split
                            uint256 xSplit = xpBefore[i] + dxSplitNormalized;
                            uint256 ySplit = CurveMath.get_y(i, j, xSplit, xpBefore, currentA);
                            uint256 dySplitNormalized = xpBefore[j] - ySplit;
                            uint256 dyRestNormalized = dyNormalized - dySplitNormalized;

                            uint256 feeBasePart = (dySplitNormalized * baseFee) / FEE_DENOMINATOR;
                            uint256 feeKinkPart = (dyRestNormalized * kinkingFee) / FEE_DENOMINATOR;
                            uint256 totalFee = feeBasePart + feeKinkPart;

                            uint256 adminShareBase = (feeBasePart * baseFeeShare) / FEE_DENOMINATOR;
                            uint256 adminShareKink = (feeKinkPart * kinkingFeeShare) / FEE_DENOMINATOR;
                            uint256 totalAdminShare = adminShareBase + adminShareKink;

                            if (totalAdminShare > 0) {
                                adminFeeAmount += totalAdminShare / tokenMultipliers[j];
                            }
                            dyNormalized -= totalFee;

                        } else {
                            // Started below peg
                            fee = kinkingFee;
                            uint256 dyFeeTotal = (dyNormalized * fee) / FEE_DENOMINATOR;
                            uint256 adminShare = (dyFeeTotal * kinkingFeeShare) / FEE_DENOMINATOR;
                            if (adminShare > 0) {
                                adminFeeAmount += adminShare / tokenMultipliers[j];
                            }
                            dyNormalized -= dyFeeTotal;
                        }
                    } else {
                        // End price >= peg. Base fee.
                        uint256 dyFeeTotal = (dyNormalized * baseFee) / FEE_DENOMINATOR;
                        uint256 adminShare = (dyFeeTotal * baseFeeShare) / FEE_DENOMINATOR;
                        if (adminShare > 0) {
                            adminFeeAmount += adminShare / tokenMultipliers[j];
                        }
                        dyNormalized -= dyFeeTotal;
                    }
                 }
            } else {
                // Converging
                uint256 dyFeeTotal = (dyNormalized * baseFee) / FEE_DENOMINATOR;
                uint256 adminShare = (dyFeeTotal * baseFeeShare) / FEE_DENOMINATOR;
                if (adminShare > 0) {
                    adminFeeAmount += adminShare / tokenMultipliers[j];
                }
                dyNormalized -= dyFeeTotal;
            }

            dy = dyNormalized / tokenMultipliers[j];
        }
    }

    /**
     * @notice Calculate output amount for a given input (view only)
     * @param i Index of input token (0 or 1)
     * @param j Index of output token (0 or 1)
     * @param dx Input amount
     * @return dy Output amount
     */
    function get_dy(uint256 i, uint256 j, uint256 dx) external view returns (uint256 dy) {
        require(i != j && i < N_COINS && j < N_COINS, "KinkPool: Invalid indices");
        require(dx > 0, "KinkPool: Zero input");

        uint256[N_COINS] memory balances = _balances();
        uint256[N_COINS] memory xpBefore = _xp(balances);

        (dy, ) = _calculate_exchange(i, j, dx, xpBefore);
    }

    /**
     * @notice Execute a swap
     * @param i Index of input token (0 or 1)
     * @param j Index of output token (0 or 1)
     * @param dx Input amount
     * @param min_dy Minimum output amount (slippage protection)
     * @return dy Output amount
     */
    function exchange(
        uint256 i,
        uint256 j,
        uint256 dx,
        uint256 min_dy
    ) external nonReentrant returns (uint256 dy) {
        require(i != j && i < N_COINS && j < N_COINS, "KinkPool: Invalid indices");
        require(dx > 0, "KinkPool: Zero input");

        IERC20 inputToken = i == 0 ? IERC20(token0) : IERC20(token1);
        IERC20 outputToken = j == 0 ? IERC20(token0) : IERC20(token1);

        uint256[N_COINS] memory reservesBefore = _balances();

        // Fix #1: Use raw balance for input calculation to prevent admin fee theft
        uint256 inputBalanceBefore = IERC20(address(inputToken)).balanceOf(address(this));

        // Transfer input tokens
        inputToken.safeTransferFrom(msg.sender, address(this), dx);

        uint256 inputBalanceAfter = IERC20(address(inputToken)).balanceOf(address(this));
        require(inputBalanceAfter > inputBalanceBefore, "KinkPool: Insufficient input");
        uint256 actualDx = inputBalanceAfter - inputBalanceBefore;

        uint256[N_COINS] memory xpBefore = _xp(reservesBefore);

        uint256 adminAmount;
        (dy, adminAmount) = _calculate_exchange(i, j, actualDx, xpBefore);

        // Update admin fees
        if (adminAmount > 0) {
            if (j == 0) adminFee0 += adminAmount;
            else adminFee1 += adminAmount;
        }

        require(dy >= min_dy, "KinkPool: Slippage");
        require(dy > 0, "KinkPool: Insufficient output");

        uint256 outputBalanceBeforeTransfer = IERC20(address(outputToken)).balanceOf(address(this));
        require(outputBalanceBeforeTransfer >= dy, "KinkPool: Insufficient liquidity");

        outputToken.safeTransfer(msg.sender, dy);

        uint256 outputBalanceAfterTransfer = IERC20(address(outputToken)).balanceOf(address(this));
        uint256 actualDy = outputBalanceBeforeTransfer - outputBalanceAfterTransfer;
        require(actualDy > 0, "KinkPool: Transfer failed");

        if (actualDy != dy) {
            require(actualDy >= min_dy, "KinkPool: Actual output below minimum");
            dy = actualDy;
        }

        emit Exchange(msg.sender, msg.sender, i, j, actualDx, dy);
    }

    /**
     * @notice Add liquidity to the pool
     * @dev Mitigates A-Switch valuation attacks by forcing the use of the higher A
     *      when crossing equilibrium.
     * @param amounts Array of amounts to add [token0, token1]
     * @param min_lp Minimum LP tokens to mint (slippage protection)
     * @return lpAmount Amount of LP tokens minted
     */
    function add_liquidity(
        uint256[N_COINS] memory amounts,
        uint256 min_lp
    ) external nonReentrant returns (uint256 lpAmount) {
        require(amounts[0] > 0 || amounts[1] > 0, "KinkPool: Zero amounts");

        uint256[N_COINS] memory balancesBefore = _balances();
        uint256 totalSupply = totalSupply();

        // Transfer tokens
        if (amounts[0] > 0) {
            IERC20(token0).safeTransferFrom(msg.sender, address(this), amounts[0]);
        }
        if (amounts[1] > 0) {
            IERC20(token1).safeTransferFrom(msg.sender, address(this), amounts[1]);
        }

        uint256[N_COINS] memory balancesAfter = _balances();

        uint256[N_COINS] memory xpAfter = _xp(balancesAfter);
        uint256 A_new = _get_A(xpAfter);

        if (totalSupply == 0) {
            uint256 D1 = CurveMath.get_D(xpAfter, A_new);
            require(D1 > 0, "KinkPool: Invalid D");
            lpAmount = D1;
            require(lpAmount > MINIMUM_LIQUIDITY, "KinkPool: Insufficient liquidity minted");
            // Burn the minimum liquidity to lock the price
            _mint(address(0xdEaD), MINIMUM_LIQUIDITY);
            // Mint the rest to the sender
            lpAmount -= MINIMUM_LIQUIDITY;
        } else {
            uint256[N_COINS] memory xpBefore = _xp(balancesBefore);
            uint256 A_old = _get_A(xpBefore);

            // Use the MAX A for the calculation to prevent valuation arbitrage
            // If we move Low -> High, we use High (suppresses minting).
            // If we move High -> Low, we use High (suppresses minting).
            uint256 A_calc = A_old > A_new ? A_old : A_new;

            uint256 D0 = CurveMath.get_D(xpBefore, A_calc);
            uint256 D1 = CurveMath.get_D(xpAfter, A_calc);
            require(D1 > D0, "KinkPool: D must increase");

            // Calculate LP tokens to mint
            lpAmount = (totalSupply * (D1 - D0)) / D0;
        }

        require(lpAmount >= min_lp, "KinkPool: Slippage");
        _mint(msg.sender, lpAmount);

        emit AddLiquidity(msg.sender, amounts, lpAmount);
    }

    /**
     * @notice Remove liquidity from the pool
     * @param lpAmount Amount of LP tokens to burn
     * @param min_amounts Minimum amounts to receive [token0, token1]
     * @return amounts Array of amounts withdrawn [token0, token1]
     */
    function remove_liquidity(
        uint256 lpAmount,
        uint256[N_COINS] memory min_amounts
    ) external nonReentrant returns (uint256[N_COINS] memory amounts) {
        require(lpAmount > 0, "KinkPool: Zero amount");

        uint256 totalSupply = totalSupply();
        uint256[N_COINS] memory balances = _balances();

        // Calculate amounts to withdraw
        for (uint256 i = 0; i < N_COINS; i++) {
            amounts[i] = (balances[i] * lpAmount) / totalSupply;
            require(amounts[i] >= min_amounts[i], "KinkPool: Slippage");
        }

        // Burn LP tokens
        _burn(msg.sender, lpAmount);

        // Transfer tokens
        if (amounts[0] > 0) {
            IERC20(token0).safeTransfer(msg.sender, amounts[0]);
        }
        if (amounts[1] > 0) {
            IERC20(token1).safeTransfer(msg.sender, amounts[1]);
        }

        emit RemoveLiquidity(msg.sender, amounts, lpAmount);
    }

    /**
     * @notice Calculate expected LP tokens for a given deposit
     * @param amounts Array of amounts to add [token0, token1]
     * @param is_deposit True if depositing, False if withdrawing (not used currently but standard signature)
     * @return Expected LP amount
     */
    function calc_token_amount(
        uint256[N_COINS] memory amounts,
        bool is_deposit
    ) external view returns (uint256) {
        uint256[N_COINS] memory balances = _balances();
        uint256 totalSupply = totalSupply();

        uint256[N_COINS] memory xpBefore = _xp(balances);
        uint256 A_old = _get_A(xpBefore);

        uint256[N_COINS] memory new_balances = balances;
        for (uint256 i = 0; i < N_COINS; i++) {
            if (is_deposit) {
                new_balances[i] += amounts[i];
            } else {
                // Logic for withdrawal would differ
                if (amounts[i] > new_balances[i]) return 0;
                new_balances[i] -= amounts[i];
            }
        }

        uint256[N_COINS] memory xpAfter = _xp(new_balances);
        uint256 A_new = _get_A(xpAfter);

        if (totalSupply == 0) {
            uint256 D1 = CurveMath.get_D(xpAfter, A_new);
            if (D1 <= MINIMUM_LIQUIDITY) return 0;
            return D1 - MINIMUM_LIQUIDITY;
        }

        // Use Max A logic
        uint256 A_calc = A_old > A_new ? A_old : A_new;
        uint256 D0 = CurveMath.get_D(xpBefore, A_calc);
        uint256 D1 = CurveMath.get_D(xpAfter, A_calc);

        if (D1 > D0) {
             return (totalSupply * (D1 - D0)) / D0;
        } else {
             return (totalSupply * (D0 - D1)) / D0;
        }
    }

    /**
     * @notice Get current reserves
     * @return reserve0 Reserve of token0
     * @return reserve1 Reserve of token1
     */
    function getReserves() external view returns (uint256 reserve0, uint256 reserve1) {
        uint256[N_COINS] memory balances = _balances();
        reserve0 = balances[0];
        reserve1 = balances[1];
    }

    /**
     * @notice Square root function (Babylonian method)
     */
    function sqrt(uint256 x) internal pure returns (uint256) {
        if (x == 0) return 0;
        uint256 z = (x + 1) / 2;
        uint256 y = x;
        while (z < y) {
            y = z;
            z = (x / z + z) / 2;
        }
        return y;
    }
}
