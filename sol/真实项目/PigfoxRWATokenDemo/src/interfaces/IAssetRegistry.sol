// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title IAssetRegistry
/// @notice The single method redemption needs from the asset registry: whether
///         an asset id is registered and currently active for redemption.
interface IAssetRegistry {
    /// @notice True when `assetId` exists and its status is Active.
    /// @param assetId The asset to test.
    /// @return True only when the asset exists AND is Active — an unknown id answers
    ///         false, so redemption cannot proceed against an asset that was never
    ///         registered.
    function isActive(uint256 assetId) external view returns (bool);
}
