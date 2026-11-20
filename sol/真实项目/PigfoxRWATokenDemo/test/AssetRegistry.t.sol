// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {BaseTest} from "./Base.t.sol";
import {Roles} from "../src/Roles.sol";
import {AssetRegistry} from "../src/AssetRegistry.sol";

contract AssetRegistryTest is BaseTest {
    /*//////////////////////////////////////////////////////////////
                                REGISTER
    //////////////////////////////////////////////////////////////*/

    function test_Register_Succeeds() public {
        assertEq(assets.assetCount(), 0, "starts empty");
        vm.expectEmit(true, false, false, true);
        emit AssetRegistry.AssetRegistered(0, DOC_HASH, DOC_URI);
        vm.prank(owner);
        uint256 id = assets.registerAsset(DOC_HASH, DOC_URI);
        assertEq(id, 0, "first id is zero");
        assertEq(assets.assetCount(), 1, "count incremented");

        AssetRegistry.Asset memory a = assets.getAsset(id);
        assertEq(a.docHash, DOC_HASH, "docHash");
        assertEq(a.uri, DOC_URI, "uri");
        assertTrue(a.status == AssetRegistry.Status.Active, "active");
        assertTrue(a.exists, "exists");
        assertTrue(assets.isActive(id), "isActive");
    }

    function test_Register_AssignsSequentialIds() public {
        vm.startPrank(owner);
        uint256 a = assets.registerAsset(DOC_HASH, DOC_URI);
        uint256 b = assets.registerAsset(keccak256("second"), "ipfs://second");
        vm.stopPrank();
        assertEq(a, 0, "first");
        assertEq(b, 1, "second");
        assertEq(assets.assetCount(), 2, "count");
    }

    function test_Register_RevertsForNonAgent() public {
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(Roles.NotAgent.selector, stranger));
        assets.registerAsset(DOC_HASH, DOC_URI);
    }

    /*//////////////////////////////////////////////////////////////
                              SET STATUS
    //////////////////////////////////////////////////////////////*/

    function test_SetStatus_Succeeds() public {
        uint256 id = _registerAsset();
        vm.expectEmit(true, false, false, true);
        emit AssetRegistry.AssetStatusUpdated(id, AssetRegistry.Status.Active, AssetRegistry.Status.Suspended);
        vm.prank(owner);
        assets.setAssetStatus(id, AssetRegistry.Status.Suspended);
        assertFalse(assets.isActive(id), "no longer active");
        assertTrue(assets.getAsset(id).status == AssetRegistry.Status.Suspended, "suspended");
    }

    function test_SetStatus_RevertsOnUnknownAsset() public {
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(AssetRegistry.UnknownAsset.selector, 99));
        assets.setAssetStatus(99, AssetRegistry.Status.Suspended);
    }

    function test_SetStatus_RevertsOnNoneStatus() public {
        uint256 id = _registerAsset();
        vm.prank(owner);
        vm.expectRevert(AssetRegistry.InvalidStatus.selector);
        assets.setAssetStatus(id, AssetRegistry.Status.None);
    }

    function test_SetStatus_RevertsForNonAgent() public {
        uint256 id = _registerAsset();
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(Roles.NotAgent.selector, stranger));
        assets.setAssetStatus(id, AssetRegistry.Status.Suspended);
    }

    /*//////////////////////////////////////////////////////////////
                                  VIEWS
    //////////////////////////////////////////////////////////////*/

    function test_GetAsset_RevertsOnUnknown() public {
        vm.expectRevert(abi.encodeWithSelector(AssetRegistry.UnknownAsset.selector, 0));
        assets.getAsset(0);
    }

    function test_IsActive_FalseForUnknown() public view {
        assertFalse(assets.isActive(123), "unknown is not active");
    }

    function test_IsActive_FalseAfterRedeemed() public {
        uint256 id = _registerAsset();
        vm.prank(owner);
        assets.setAssetStatus(id, AssetRegistry.Status.Redeemed);
        assertFalse(assets.isActive(id), "redeemed is not active");
    }
}
