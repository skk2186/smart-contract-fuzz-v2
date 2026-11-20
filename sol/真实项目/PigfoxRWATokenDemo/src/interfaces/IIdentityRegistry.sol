// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title IIdentityRegistry
/// @notice The single method the token needs from the KYC whitelist: a yes/no
///         verification check on an address.
interface IIdentityRegistry {
    /// @notice True when `account` is a KYC-verified identity permitted to hold
    ///         and transact the token.
    /// @param account The address to test.
    /// @return True while whitelisted. Consulted fresh on every mint and transfer rather
    ///         than cached, so a removal takes effect on the very next movement.
    function isVerified(address account) external view returns (bool);
}
