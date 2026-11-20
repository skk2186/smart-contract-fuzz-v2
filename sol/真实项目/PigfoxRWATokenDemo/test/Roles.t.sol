// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {BaseTest} from "./Base.t.sol";
import {Roles} from "../src/Roles.sol";
import {IdentityRegistry} from "../src/IdentityRegistry.sol";

/// @dev Exercises the shared Roles base through a concrete IdentityRegistry.
contract RolesTest is BaseTest {
    /*//////////////////////////////////////////////////////////////
                              CONSTRUCTOR
    //////////////////////////////////////////////////////////////*/

    function test_Constructor_SetsOwnerAndFirstAgent() public {
        IdentityRegistry fresh = new IdentityRegistry(owner);
        assertEq(fresh.owner(), owner, "owner");
        assertTrue(fresh.agents(owner), "owner is agent");
    }

    function test_Constructor_RevertsOnZeroOwner() public {
        vm.expectRevert(Roles.ZeroAddress.selector);
        new IdentityRegistry(address(0));
    }

    function test_Constructor_EmitsOwnershipAndAgent() public {
        vm.expectEmit(true, true, false, false);
        emit Roles.OwnershipTransferred(address(0), owner);
        vm.expectEmit(true, false, false, true);
        emit Roles.AgentSet(owner, true);
        new IdentityRegistry(owner);
    }

    /*//////////////////////////////////////////////////////////////
                           TRANSFER OWNERSHIP
    //////////////////////////////////////////////////////////////*/

    function test_TransferOwnership_Succeeds() public {
        vm.expectEmit(true, true, false, false);
        emit Roles.OwnershipTransferred(owner, alice);
        vm.prank(owner);
        identity.transferOwnership(alice);
        assertEq(identity.owner(), alice, "new owner");
    }

    function test_TransferOwnership_DoesNotGrantAgentRole() public {
        vm.prank(owner);
        identity.transferOwnership(carol);
        assertFalse(identity.agents(carol), "new owner is not auto-agent");
    }

    function test_TransferOwnership_RevertsOnZero() public {
        vm.prank(owner);
        vm.expectRevert(Roles.ZeroAddress.selector);
        identity.transferOwnership(address(0));
    }

    function test_TransferOwnership_RevertsWhenNotOwner() public {
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(Roles.NotOwner.selector, stranger));
        identity.transferOwnership(stranger);
    }

    /*//////////////////////////////////////////////////////////////
                                SET AGENT
    //////////////////////////////////////////////////////////////*/

    function test_SetAgent_EnablesAndDisables() public {
        vm.expectEmit(true, false, false, true);
        emit Roles.AgentSet(alice, true);
        vm.prank(owner);
        identity.setAgent(alice, true);
        assertTrue(identity.agents(alice), "enabled");

        vm.prank(owner);
        identity.setAgent(alice, false);
        assertFalse(identity.agents(alice), "disabled");
    }

    function test_SetAgent_RevertsOnZero() public {
        vm.prank(owner);
        vm.expectRevert(Roles.ZeroAddress.selector);
        identity.setAgent(address(0), true);
    }

    function test_SetAgent_RevertsWhenNotOwner() public {
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(Roles.NotOwner.selector, stranger));
        identity.setAgent(stranger, true);
    }

    /*//////////////////////////////////////////////////////////////
                              ONLY AGENT
    //////////////////////////////////////////////////////////////*/

    function test_OnlyAgent_RevertsForNonAgent() public {
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(Roles.NotAgent.selector, stranger));
        identity.registerIdentity(carol);
    }

    function test_OnlyAgent_AllowsGrantedAgent() public {
        vm.prank(owner);
        identity.setAgent(alice, true);
        vm.prank(alice);
        identity.registerIdentity(carol); // does not revert
        assertTrue(identity.isVerified(carol), "granted agent can register");
    }
}
