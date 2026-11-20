// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {BaseTest} from "./Base.t.sol";
import {Roles} from "../src/Roles.sol";
import {RWAToken} from "../src/RWAToken.sol";
import {Redemption} from "../src/Redemption.sol";

contract RedemptionTest is BaseTest {
    uint256 internal constant AMOUNT = 1_000 ether;

    /*//////////////////////////////////////////////////////////////
                              CONSTRUCTOR
    //////////////////////////////////////////////////////////////*/

    function test_Constructor_SetsRefs() public view {
        assertEq(address(redemption.token()), address(token), "token");
        assertEq(address(redemption.assetRegistry()), address(assets), "assetRegistry");
        assertEq(redemption.requestCount(), 0, "starts empty");
    }

    function test_Constructor_RevertsOnZeroToken() public {
        vm.expectRevert(Roles.ZeroAddress.selector);
        new Redemption(address(0), address(assets), owner);
    }

    function test_Constructor_RevertsOnZeroAssetRegistry() public {
        vm.expectRevert(Roles.ZeroAddress.selector);
        new Redemption(address(token), address(0), owner);
    }

    /*//////////////////////////////////////////////////////////////
                          REQUEST REDEMPTION
    //////////////////////////////////////////////////////////////*/

    function test_Request_Succeeds() public {
        uint256 assetId = _registerAsset();
        _mint(alice, AMOUNT);

        vm.expectEmit(true, true, true, true);
        emit Redemption.RedemptionRequested(0, alice, assetId, 300 ether);
        vm.prank(alice);
        uint256 reqId = redemption.requestRedemption(assetId, 300 ether);

        assertEq(reqId, 0, "first request id");
        assertEq(redemption.requestCount(), 1, "count");
        assertEq(token.balanceOf(alice), 700 ether, "tokens burned");
        assertEq(token.totalSupply(), 700 ether, "supply reduced");

        Redemption.Request memory r = redemption.getRequest(reqId);
        assertEq(r.holder, alice, "holder");
        assertEq(r.assetId, assetId, "assetId");
        assertEq(r.amount, 300 ether, "amount");
        assertFalse(r.settled, "not settled");
        assertTrue(r.exists, "exists");
    }

    function test_Request_RevertsOnZeroAmount() public {
        uint256 assetId = _registerAsset();
        vm.prank(alice);
        vm.expectRevert(Redemption.ZeroAmount.selector);
        redemption.requestRedemption(assetId, 0);
    }

    function test_Request_RevertsWhenAssetNotActive() public {
        // no asset registered → id 0 is not active
        _mint(alice, AMOUNT);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Redemption.AssetNotActive.selector, 0));
        redemption.requestRedemption(0, 1 ether);
    }

    function test_Request_RevertsWhenHolderLacksBalance() public {
        uint256 assetId = _registerAsset();
        // alice is verified but holds nothing → token burn reverts
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(RWAToken.InsufficientBalance.selector, alice, 0, 1 ether));
        redemption.requestRedemption(assetId, 1 ether);
    }

    /*//////////////////////////////////////////////////////////////
                          SETTLE REDEMPTION
    //////////////////////////////////////////////////////////////*/

    function test_Settle_Succeeds() public {
        uint256 reqId = _seedRequest();
        vm.expectEmit(true, false, false, false);
        emit Redemption.RedemptionSettled(reqId);
        vm.prank(owner);
        redemption.settleRedemption(reqId);
        assertTrue(redemption.getRequest(reqId).settled, "settled");
    }

    function test_Settle_RevertsOnUnknownRequest() public {
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(Redemption.UnknownRequest.selector, 42));
        redemption.settleRedemption(42);
    }

    function test_Settle_RevertsWhenAlreadySettled() public {
        uint256 reqId = _seedRequest();
        vm.prank(owner);
        redemption.settleRedemption(reqId);
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(Redemption.AlreadySettled.selector, reqId));
        redemption.settleRedemption(reqId);
    }

    function test_Settle_RevertsForNonAgent() public {
        uint256 reqId = _seedRequest();
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(Roles.NotAgent.selector, stranger));
        redemption.settleRedemption(reqId);
    }

    /*//////////////////////////////////////////////////////////////
                                  VIEWS
    //////////////////////////////////////////////////////////////*/

    function test_GetRequest_RevertsOnUnknown() public {
        vm.expectRevert(abi.encodeWithSelector(Redemption.UnknownRequest.selector, 0));
        redemption.getRequest(0);
    }

    /*//////////////////////////////////////////////////////////////
                                 HELPERS
    //////////////////////////////////////////////////////////////*/

    function _seedRequest() internal returns (uint256 reqId) {
        uint256 assetId = _registerAsset();
        _mint(alice, AMOUNT);
        vm.prank(alice);
        reqId = redemption.requestRedemption(assetId, 300 ether);
    }
}
