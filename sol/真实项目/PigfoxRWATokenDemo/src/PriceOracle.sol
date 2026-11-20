// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Roles} from "./Roles.sol";

/// @title PriceOracle
/// @notice A mock push oracle for the asset's per-token price. An updater agent
///         pushes a new price; every push stamps `updatedAt` with the block
///         timestamp so consumers can reason about staleness.
/// @dev `updatedAt` is monotonically non-decreasing: it is only ever assigned
///      `block.timestamp`, which never moves backwards between transactions.
contract PriceOracle is Roles {
    /*//////////////////////////////////////////////////////////////
                                 ERRORS
    //////////////////////////////////////////////////////////////*/

    /// @notice No price has been pushed yet, so the query is undefined.
    error NoPrice();

    /*//////////////////////////////////////////////////////////////
                                 EVENTS
    //////////////////////////////////////////////////////////////*/

    /// @notice Emitted on every price push.
    /// @param price The pushed price, in the oracle's own unit.
    /// @param updatedAt The block timestamp stamped onto the push. Emitted on every call,
    ///        including one that pushes an unchanged price, so a consumer can distinguish
    ///        "the price is still this" from "nobody has updated it".
    event PriceUpdated(uint256 price, uint256 updatedAt);

    /*//////////////////////////////////////////////////////////////
                                 STORAGE
    //////////////////////////////////////////////////////////////*/

    /// @notice Latest pushed price, in the oracle's own unit (e.g. USD cents per token).
    uint256 public price;
    /// @notice Block timestamp of the latest push. Zero until the first update.
    uint256 public updatedAt;

    /// @notice Deploys the oracle with no price yet published.
    /// @param initialOwner The deployer; owner and first (updater) agent.
    constructor(address initialOwner) Roles(initialOwner) {}

    /*//////////////////////////////////////////////////////////////
                                 UPDATER
    //////////////////////////////////////////////////////////////*/

    /// @notice Push a new price. Stamps `updatedAt` with the current block time.
    /// @param newPrice The price to publish. Zero is accepted deliberately: this is a mock
    ///        push oracle, and rejecting zero would make "the asset is worthless" the one
    ///        state it could not report.
    function setPrice(uint256 newPrice) external onlyAgent {
        price = newPrice;
        updatedAt = block.timestamp;
        emit PriceUpdated(newPrice, block.timestamp);
    }

    /*//////////////////////////////////////////////////////////////
                                  VIEWS
    //////////////////////////////////////////////////////////////*/

    /// @notice The latest price and the timestamp it was pushed. Reverts if
    ///         no price has ever been set.
    /// @return currentPrice The latest pushed price.
    /// @return at The timestamp it was pushed, so the caller can judge staleness itself
    ///         rather than trusting the oracle's own verdict.
    function latestPrice() external view returns (uint256 currentPrice, uint256 at) {
        if (updatedAt == 0) revert NoPrice();
        return (price, updatedAt);
    }

    /// @notice True when the latest price is older than `maxAge` seconds.
    /// @dev Reverts if no price has ever been pushed; staleness is undefined then.
    /// @param maxAge The oldest age in seconds still considered fresh. Compared with a
    ///        strict `>`, so a price exactly `maxAge` old is still fresh.
    /// @return True when the latest push is older than `maxAge`.
    function isStale(uint256 maxAge) external view returns (bool) {
        if (updatedAt == 0) revert NoPrice();
        return block.timestamp - updatedAt > maxAge;
    }
}
