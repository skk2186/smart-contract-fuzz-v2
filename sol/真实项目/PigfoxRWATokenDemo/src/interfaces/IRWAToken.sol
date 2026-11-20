// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title IRWAToken
/// @notice The subset of the token surface that sibling contracts depend on:
///         the identity registry reads balances to guard de-verification, and
///         the redemption contract burns tokens against a registered asset.
interface IRWAToken {
    /// @notice The token balance of `account`.
    /// @param account The address to read.
    /// @return The balance. Read by the identity registry to refuse de-verifying a holder.
    function balanceOf(address account) external view returns (uint256);

    /// @notice Burn `amount` tokens held by `from`. Restricted to the token's
    ///         configured redeemer.
    /// @param from The holder whose tokens are destroyed.
    /// @param amount The quantity to burn, also deducted from total supply.
    function burnFrom(address from, uint256 amount) external;
}
