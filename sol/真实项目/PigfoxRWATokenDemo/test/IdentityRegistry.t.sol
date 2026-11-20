// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {BaseTest} from "./Base.t.sol";
import {Roles} from "../src/Roles.sol";
import {IdentityRegistry} from "../src/IdentityRegistry.sol";

contract IdentityRegistryTest is BaseTest {
    /*//////////////////////////////////////////////////////////////
                                REGISTER
    //////////////////////////////////////////////////////////////*/

    function test_Register_Succeeds() public {
        assertFalse(identity.isVerified(carol), "carol starts unverified");
        vm.expectEmit(true, false, false, false);
        emit IdentityRegistry.IdentityRegistered(carol);
        vm.prank(owner);
        identity.registerIdentity(carol);
        assertTrue(identity.isVerified(carol), "carol verified");
    }

    function test_Register_RevertsOnZero() public {
        vm.prank(owner);
        vm.expectRevert(Roles.ZeroAddress.selector);
        identity.registerIdentity(address(0));
    }

    function test_Register_RevertsIfAlreadyVerified() public {
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(IdentityRegistry.AlreadyVerified.selector, alice));
        identity.registerIdentity(alice); // alice registered in setUp
    }

    function test_Register_RevertsForNonAgent() public {
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(Roles.NotAgent.selector, stranger));
        identity.registerIdentity(carol);
    }

    /*//////////////////////////////////////////////////////////////
                                 REMOVE
    //////////////////////////////////////////////////////////////*/

    function test_Remove_Succeeds() public {
        vm.expectEmit(true, false, false, false);
        emit IdentityRegistry.IdentityRemoved(alice);
        vm.prank(owner);
        identity.removeIdentity(alice);
        assertFalse(identity.isVerified(alice), "alice removed");
    }

    function test_Remove_RevertsIfNotVerified() public {
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(IdentityRegistry.NotVerifiedIdentity.selector, carol));
        identity.removeIdentity(carol);
    }

    function test_Remove_RevertsForNonAgent() public {
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(Roles.NotAgent.selector, stranger));
        identity.removeIdentity(alice);
    }

    function test_Remove_RevertsWhenHolderHasBalance() public {
        _mint(alice, 1_000 ether);
        vm.prank(owner);
        vm.expectRevert(
            abi.encodeWithSelector(IdentityRegistry.HolderHasBalance.selector, alice, 1_000 ether)
        );
        identity.removeIdentity(alice);
    }

    function test_Remove_SucceedsAfterBalanceCleared() public {
        _mint(alice, 1_000 ether);
        // burn it all back via the redemption wiring path (redeemer = redemption)
        vm.prank(address(redemption));
        token.burnFrom(alice, 1_000 ether);
        vm.prank(owner);
        identity.removeIdentity(alice); // now allowed
        assertFalse(identity.isVerified(alice), "removed after balance cleared");
    }

    /*//////////////////////////////////////////////////////////////
                                SET TOKEN
    //////////////////////////////////////////////////////////////*/

    function test_SetToken_Succeeds() public {
        // deploy a fresh registry with no token bound
        vm.prank(owner);
        IdentityRegistry fresh = new IdentityRegistry(owner);
        vm.expectEmit(true, false, false, false);
        emit IdentityRegistry.TokenSet(address(token));
        vm.prank(owner);
        fresh.setToken(address(token));
        assertEq(address(fresh.token()), address(token), "token bound");
    }

    function test_SetToken_RevertsOnZero() public {
        vm.prank(owner);
        IdentityRegistry fresh = new IdentityRegistry(owner);
        vm.prank(owner);
        vm.expectRevert(Roles.ZeroAddress.selector);
        fresh.setToken(address(0));
    }

    function test_SetToken_RevertsWhenAlreadySet() public {
        // the Base fixture already bound the token on `identity`
        vm.prank(owner);
        vm.expectRevert(IdentityRegistry.TokenAlreadySet.selector);
        identity.setToken(address(token));
    }

    function test_SetToken_RevertsForNonOwner() public {
        vm.prank(owner);
        IdentityRegistry fresh = new IdentityRegistry(owner);
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(Roles.NotOwner.selector, stranger));
        fresh.setToken(address(token));
    }

    /*//////////////////////////////////////////////////////////////
                            REMOVE (NO TOKEN)
    //////////////////////////////////////////////////////////////*/

    function test_Remove_SucceedsWhenNoTokenBound() public {
        // fresh registry with no token bound → balance guard is skipped
        vm.startPrank(owner);
        IdentityRegistry fresh = new IdentityRegistry(owner);
        fresh.registerIdentity(alice);
        fresh.removeIdentity(alice);
        vm.stopPrank();
        assertFalse(fresh.isVerified(alice), "removed with no token guard");
    }
}
