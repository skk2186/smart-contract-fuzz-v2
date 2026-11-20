// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title Actor — a callable stand-in for a token holder.
/// @notice Echidna and Medusa have no cheatcodes, so a harness that needs a call
///         to arrive from a specific `msg.sender` cannot prank one: it has to own
///         a contract at that address and call through it. That is all this is.
///
/// @dev    It matters here specifically because `Redemption.requestRedemption`
///         records `msg.sender` as the holder and burns that account's tokens.
///         Without distinct actors every redemption in a campaign would be the
///         harness redeeming from itself, and the ledger invariants would only
///         ever see one holder — which is exactly the shape of a bug they are
///         meant to catch.
contract Actor {
    /// @notice Forwards `data` to `target` and reports whether it succeeded.
    /// @dev Returns the outcome rather than bubbling the revert. The harness
    ///      compares outcomes against what it expected; a bubbled revert would
    ///      abort the fuzzer's transaction instead, which turns an interesting
    ///      state into a discarded one.
    function call(address target, bytes calldata data) external returns (bool ok, bytes memory ret) {
        // solhint-disable-next-line avoid-low-level-calls
        (ok, ret) = target.call(data);
    }
}
