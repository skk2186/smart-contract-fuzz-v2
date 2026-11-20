// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {BaseTest} from "./Base.t.sol";
import {Roles} from "../src/Roles.sol";
import {PriceOracle} from "../src/PriceOracle.sol";

contract PriceOracleTest is BaseTest {
    uint256 internal constant PRICE = 12_345; // e.g. USD cents per token

    /*//////////////////////////////////////////////////////////////
                                SET PRICE
    //////////////////////////////////////////////////////////////*/

    function test_SetPrice_Succeeds() public {
        vm.warp(1_700_000_000);
        vm.expectEmit(false, false, false, true);
        emit PriceOracle.PriceUpdated(PRICE, block.timestamp);
        vm.prank(owner);
        oracle.setPrice(PRICE);
        assertEq(oracle.price(), PRICE, "price stored");
        assertEq(oracle.updatedAt(), block.timestamp, "timestamp stamped");
    }

    function test_SetPrice_RevertsForNonAgent() public {
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(Roles.NotAgent.selector, stranger));
        oracle.setPrice(PRICE);
    }

    /*//////////////////////////////////////////////////////////////
                              LATEST PRICE
    //////////////////////////////////////////////////////////////*/

    function test_LatestPrice_RevertsBeforeFirstPush() public {
        vm.expectRevert(PriceOracle.NoPrice.selector);
        oracle.latestPrice();
    }

    function test_LatestPrice_ReturnsPriceAndTimestamp() public {
        vm.warp(1_700_000_500);
        vm.prank(owner);
        oracle.setPrice(PRICE);
        (uint256 p, uint256 at) = oracle.latestPrice();
        assertEq(p, PRICE, "price");
        assertEq(at, 1_700_000_500, "timestamp");
    }

    /*//////////////////////////////////////////////////////////////
                                STALENESS
    //////////////////////////////////////////////////////////////*/

    function test_IsStale_RevertsBeforeFirstPush() public {
        vm.expectRevert(PriceOracle.NoPrice.selector);
        oracle.isStale(60);
    }

    function test_IsStale_FalseWhenFresh() public {
        vm.warp(1_700_000_000);
        vm.prank(owner);
        oracle.setPrice(PRICE);
        vm.warp(1_700_000_030); // 30s later
        assertFalse(oracle.isStale(60), "within maxAge is fresh");
    }

    function test_IsStale_TrueWhenOld() public {
        vm.warp(1_700_000_000);
        vm.prank(owner);
        oracle.setPrice(PRICE);
        vm.warp(1_700_000_200); // 200s later
        assertTrue(oracle.isStale(60), "beyond maxAge is stale");
    }

    /*//////////////////////////////////////////////////////////////
                             MONOTONIC STAMP
    //////////////////////////////////////////////////////////////*/

    function test_UpdatedAt_IsMonotonic() public {
        vm.warp(1_700_000_000);
        vm.prank(owner);
        oracle.setPrice(PRICE);
        uint256 first = oracle.updatedAt();

        vm.warp(1_700_000_100);
        vm.prank(owner);
        oracle.setPrice(PRICE + 1);
        uint256 second = oracle.updatedAt();
        assertGe(second, first, "updatedAt never decreases");
    }
}
