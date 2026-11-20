// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Roles} from "./Roles.sol";
import {IRWAToken} from "./interfaces/IRWAToken.sol";
import {IIdentityRegistry} from "./interfaces/IIdentityRegistry.sol";

/// @title IdentityRegistry
/// @notice KYC whitelist for the RWA token. Agents register and remove
///         verified identities; the token consults {isVerified} on every mint
///         and transfer.
/// @dev A bound token (see {setToken}) makes the security invariant
///      "a non-verified address can never hold a non-zero balance" hold even
///      across de-verification: an identity that currently holds tokens cannot
///      be removed. Acquisition is already gated by the token's mint/transfer
///      hooks, so the only remaining escape — de-verifying a live holder — is
///      closed here.
contract IdentityRegistry is Roles, IIdentityRegistry {
    /*//////////////////////////////////////////////////////////////
                                 ERRORS
    //////////////////////////////////////////////////////////////*/

    /// @notice The identity is already verified.
    error AlreadyVerified(address account);
    /// @notice The identity is not currently verified.
    error NotVerifiedIdentity(address account);
    /// @notice The identity still holds tokens and so cannot be removed.
    error HolderHasBalance(address account, uint256 balance);
    /// @notice The bound token has already been set and is immutable thereafter.
    error TokenAlreadySet();

    /*//////////////////////////////////////////////////////////////
                                 EVENTS
    //////////////////////////////////////////////////////////////*/

    /// @notice Emitted when `account` becomes a verified identity.
    /// @param account The address added to the whitelist.
    event IdentityRegistered(address indexed account);
    /// @notice Emitted when `account` is removed from the whitelist.
    /// @param account The address removed. It necessarily held a zero balance at this
    ///        point, because `removeIdentity` refuses to strip a holder.
    event IdentityRemoved(address indexed account);
    /// @notice Emitted once when the bound token is configured.
    /// @param token The token whose balances now guard de-verification. Emitted at most
    ///        once in this contract's lifetime — `setToken` is one-shot.
    event TokenSet(address indexed token);

    /*//////////////////////////////////////////////////////////////
                                 STORAGE
    //////////////////////////////////////////////////////////////*/

    mapping(address account => bool verified) private _verified;
    /// @notice The token whose balances gate de-verification. Set once, post-deploy.
    IRWAToken public token;

    /// @notice Deploys the whitelist with no token bound and nobody verified.
    /// @param initialOwner The deployer; owner and first agent.
    constructor(address initialOwner) Roles(initialOwner) {}

    /*//////////////////////////////////////////////////////////////
                                 WIRING
    //////////////////////////////////////////////////////////////*/

    /// @notice Bind the token whose balances guard de-verification. One-shot:
    ///         reverts once set, so the guard cannot later be disabled.
    /// @param token_ The RWA token to bind. Rejected if zero, and rejected outright if a
    ///        token is already bound: re-pointing it would let an owner swap in a token
    ///        with no balances and then de-verify a holder who still owns the real one,
    ///        which is precisely the invariant this binding exists to protect.
    function setToken(address token_) external onlyOwner {
        if (token_ == address(0)) revert ZeroAddress();
        if (address(token) != address(0)) revert TokenAlreadySet();
        token = IRWAToken(token_);
        emit TokenSet(token_);
    }

    /*//////////////////////////////////////////////////////////////
                                WHITELIST
    //////////////////////////////////////////////////////////////*/

    /// @notice Add `account` to the KYC whitelist.
    /// @param account The address to verify. Rejected if zero, and rejected if already
    ///        verified — a redundant re-registration is treated as a mistake worth
    ///        surfacing rather than a silent no-op.
    function registerIdentity(address account) external onlyAgent {
        if (account == address(0)) revert ZeroAddress();
        if (_verified[account]) revert AlreadyVerified(account);
        _verified[account] = true;
        emit IdentityRegistered(account);
    }

    /// @notice Remove `account` from the KYC whitelist.
    /// @dev Reverts if a token is bound and `account` still holds a balance,
    ///      preserving the non-verified-cannot-hold invariant.
    /// @param account The address to de-verify. Reverts with `HolderHasBalance` if a token
    ///        is bound and the account still holds one, so de-verification can never
    ///        strand tokens in an address that is no longer allowed to move them.
    function removeIdentity(address account) external onlyAgent {
        if (!_verified[account]) revert NotVerifiedIdentity(account);
        if (address(token) != address(0)) {
            uint256 bal = token.balanceOf(account);
            if (bal > 0) revert HolderHasBalance(account, bal);
        }
        _verified[account] = false;
        emit IdentityRemoved(account);
    }

    /*//////////////////////////////////////////////////////////////
                                  VIEWS
    //////////////////////////////////////////////////////////////*/

    /// @notice True when `account` is a KYC-verified identity permitted to hold
    ///         and transact the token. Consulted by the token on every mint and
    ///         transfer.
    /// @param account The address to test.
    /// @return True while the address is whitelisted. A plain list membership test — unlike
    ///         zk-kyc-pass's registry there is no expiry, so verification persists until an
    ///         agent removes it.
    function isVerified(address account) external view override returns (bool) {
        return _verified[account];
    }
}
