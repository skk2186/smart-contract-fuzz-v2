// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * Representative DeFi Stateful Pattern: ERC-4626 First-Depositor Share Inflation Attack.
 * Modeled after real-world vault rounding vulnerabilities widely reported on Code4rena/Sherlock.
 *
 * Cross-account exploit chain:
 *   1. Account A approves & deposits 1 wei -> receives 1 share.
 *   2. Account A donates large assets directly to vault -> inflates share price.
 *   3. Account B approves & deposits significant assets (< donation) -> rounds down to 0 shares!
 */
contract DeFiERC4626InflationHarness {
    address public constant ACCOUNT_A = 0x0000000000000000000000000000000000010000;
    address public constant ACCOUNT_B = 0x0000000000000000000000000000000000020000;

    mapping(address => uint256) public tokenBalance;
    mapping(address => mapping(address => uint256)) public tokenAllowance;
    mapping(address => uint256) public shareBalance;
    uint256 public totalShares;
    uint256 public vaultAssets;
    bool public zeroShareLossOccurred;

    event Deposited(address indexed user, uint256 assets, uint256 shares);
    event Donated(address indexed user, uint256 assets, uint256 newVaultAssets);
    event Redeemed(address indexed user, uint256 shares, uint256 assets);

    constructor() {
        tokenBalance[ACCOUNT_A] = 10_000 ether;
        tokenBalance[ACCOUNT_B] = 10_000 ether;
    }

    function approveVault(uint256 amount) external {
        tokenAllowance[msg.sender][address(this)] = amount;
    }

    function deposit(uint256 assets) external returns (uint256 shares) {
        require(assets > 0, "ZERO_ASSETS");
        require(tokenAllowance[msg.sender][address(this)] >= assets, "ALLOWANCE_TOO_LOW");
        require(tokenBalance[msg.sender] >= assets, "BALANCE_TOO_LOW");

        if (totalShares == 0) {
            shares = assets;
        } else {
            shares = (assets * totalShares) / vaultAssets;
        }

        tokenAllowance[msg.sender][address(this)] -= assets;
        tokenBalance[msg.sender] -= assets;
        vaultAssets += assets;
        shareBalance[msg.sender] += shares;
        totalShares += shares;

        if (assets >= 1 ether && shares == 0) {
            zeroShareLossOccurred = true;
        }
        emit Deposited(msg.sender, assets, shares);
    }

    function donateToVault(uint256 assets) external {
        require(assets > 0, "ZERO_DONATION");
        require(tokenBalance[msg.sender] >= assets, "BALANCE_TOO_LOW");
        tokenBalance[msg.sender] -= assets;
        vaultAssets += assets;
        emit Donated(msg.sender, assets, vaultAssets);
    }

    function redeem(uint256 shares) external returns (uint256 assets) {
        require(shares > 0 && shareBalance[msg.sender] >= shares, "INSUFFICIENT_SHARES");
        assets = (shares * vaultAssets) / totalShares;
        shareBalance[msg.sender] -= shares;
        totalShares -= shares;
        vaultAssets -= assets;
        tokenBalance[msg.sender] += assets;
        emit Redeemed(msg.sender, shares, assets);
    }

    /// @notice Significant deposits (>= 1 ether) must never mint 0 shares due to share price manipulation.
    function echidna_no_zero_share_deposit_loss() public view returns (bool) {
        return !zeroShareLossOccurred;
    }
}
