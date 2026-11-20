// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {BaseTest} from "./Base.t.sol";
import {Roles} from "../src/Roles.sol";
import {RWAToken} from "../src/RWAToken.sol";

contract RWATokenTest is BaseTest {
    uint256 internal constant AMOUNT = 1_000 ether;

    /*//////////////////////////////////////////////////////////////
                              CONSTRUCTOR
    //////////////////////////////////////////////////////////////*/

    function test_Constructor_SetsMetadata() public view {
        assertEq(token.name(), TOKEN_NAME, "name");
        assertEq(token.symbol(), TOKEN_SYMBOL, "symbol");
        assertEq(token.decimals(), 18, "decimals");
        assertEq(address(token.identityRegistry()), address(identity), "registry");
        assertEq(token.totalSupply(), 0, "supply starts zero");
    }

    function test_Constructor_RevertsOnZeroRegistry() public {
        vm.expectRevert(Roles.ZeroAddress.selector);
        new RWAToken(TOKEN_NAME, TOKEN_SYMBOL, address(0), owner);
    }

    /*//////////////////////////////////////////////////////////////
                              SET REDEEMER
    //////////////////////////////////////////////////////////////*/

    function test_SetRedeemer_Succeeds() public {
        RWAToken fresh = _freshToken();
        vm.expectEmit(true, false, false, false);
        emit RWAToken.RedeemerSet(address(redemption));
        vm.prank(owner);
        fresh.setRedeemer(address(redemption));
        assertEq(fresh.redeemer(), address(redemption), "redeemer set");
    }

    function test_SetRedeemer_RevertsOnZero() public {
        RWAToken fresh = _freshToken();
        vm.prank(owner);
        vm.expectRevert(Roles.ZeroAddress.selector);
        fresh.setRedeemer(address(0));
    }

    function test_SetRedeemer_RevertsForNonOwner() public {
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(Roles.NotOwner.selector, stranger));
        token.setRedeemer(stranger);
    }

    /*//////////////////////////////////////////////////////////////
                                  MINT
    //////////////////////////////////////////////////////////////*/

    function test_Mint_Succeeds() public {
        vm.expectEmit(true, true, false, true);
        emit RWAToken.Transfer(address(0), alice, AMOUNT);
        _mint(alice, AMOUNT);
        assertEq(token.balanceOf(alice), AMOUNT, "balance");
        assertEq(token.totalSupply(), AMOUNT, "supply");
    }

    function test_Mint_RevertsOnZeroRecipient() public {
        vm.prank(owner);
        vm.expectRevert(Roles.ZeroAddress.selector);
        token.mint(address(0), AMOUNT);
    }

    function test_Mint_RevertsForUnverifiedRecipient() public {
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(RWAToken.RecipientNotVerified.selector, carol));
        token.mint(carol, AMOUNT);
    }

    function test_Mint_RevertsForNonAgent() public {
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(Roles.NotAgent.selector, stranger));
        token.mint(alice, AMOUNT);
    }

    /*//////////////////////////////////////////////////////////////
                                 APPROVE
    //////////////////////////////////////////////////////////////*/

    function test_Approve_Succeeds() public {
        vm.expectEmit(true, true, false, true);
        emit RWAToken.Approval(alice, bob, AMOUNT);
        vm.prank(alice);
        assertTrue(token.approve(bob, AMOUNT), "returns true");
        assertEq(token.allowance(alice, bob), AMOUNT, "allowance set");
    }

    function test_Approve_RevertsOnZeroSpender() public {
        vm.prank(alice);
        vm.expectRevert(Roles.ZeroAddress.selector);
        token.approve(address(0), AMOUNT);
    }

    /*//////////////////////////////////////////////////////////////
                                TRANSFER
    //////////////////////////////////////////////////////////////*/

    function test_Transfer_SucceedsBetweenVerified() public {
        _mint(alice, AMOUNT);
        vm.expectEmit(true, true, false, true);
        emit RWAToken.Transfer(alice, bob, 400 ether);
        vm.prank(alice);
        assertTrue(token.transfer(bob, 400 ether), "returns true");
        assertEq(token.balanceOf(alice), 600 ether, "sender debited");
        assertEq(token.balanceOf(bob), 400 ether, "recipient credited");
        assertEq(token.totalSupply(), AMOUNT, "supply unchanged");
    }

    function test_Transfer_RevertsOnZeroRecipient() public {
        _mint(alice, AMOUNT);
        vm.prank(alice);
        vm.expectRevert(Roles.ZeroAddress.selector);
        token.transfer(address(0), 1 ether);
    }

    function test_Transfer_RevertsWhenSenderNotVerified() public {
        // carol is unverified and holds nothing; the sender check fires first
        vm.prank(carol);
        vm.expectRevert(abi.encodeWithSelector(RWAToken.SenderNotVerified.selector, carol));
        token.transfer(alice, 1 ether);
    }

    function test_Transfer_RevertsWhenRecipientNotVerified() public {
        _mint(alice, AMOUNT);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(RWAToken.RecipientNotVerified.selector, carol));
        token.transfer(carol, 1 ether);
    }

    function test_Transfer_RevertsOnInsufficientBalance() public {
        _mint(alice, 10 ether);
        vm.prank(alice);
        vm.expectRevert(
            abi.encodeWithSelector(RWAToken.InsufficientBalance.selector, alice, 10 ether, 11 ether)
        );
        token.transfer(bob, 11 ether);
    }

    /*//////////////////////////////////////////////////////////////
                              TRANSFER FROM
    //////////////////////////////////////////////////////////////*/

    function test_TransferFrom_DecrementsFiniteAllowance() public {
        _mint(alice, AMOUNT);
        vm.prank(alice);
        token.approve(bob, 500 ether);

        vm.prank(bob);
        assertTrue(token.transferFrom(alice, bob, 200 ether), "returns true");
        assertEq(token.balanceOf(bob), 200 ether, "recipient credited");
        assertEq(token.allowance(alice, bob), 300 ether, "allowance decremented");
    }

    function test_TransferFrom_InfiniteAllowanceNotDecremented() public {
        _mint(alice, AMOUNT);
        vm.prank(alice);
        token.approve(bob, type(uint256).max);

        vm.prank(bob);
        token.transferFrom(alice, bob, 200 ether);
        assertEq(token.allowance(alice, bob), type(uint256).max, "infinite allowance intact");
    }

    function test_TransferFrom_RevertsOnInsufficientAllowance() public {
        _mint(alice, AMOUNT);
        vm.prank(alice);
        token.approve(bob, 100 ether);

        vm.prank(bob);
        vm.expectRevert(
            abi.encodeWithSelector(RWAToken.InsufficientAllowance.selector, alice, bob, 100 ether, 200 ether)
        );
        token.transferFrom(alice, bob, 200 ether);
    }

    /*//////////////////////////////////////////////////////////////
                                BURN FROM
    //////////////////////////////////////////////////////////////*/

    function test_BurnFrom_SucceedsForRedeemer() public {
        _mint(alice, AMOUNT);
        vm.expectEmit(true, true, false, true);
        emit RWAToken.Transfer(alice, address(0), 250 ether);
        vm.prank(address(redemption));
        token.burnFrom(alice, 250 ether);
        assertEq(token.balanceOf(alice), 750 ether, "balance reduced");
        assertEq(token.totalSupply(), 750 ether, "supply reduced");
    }

    function test_BurnFrom_RevertsForNonRedeemer() public {
        _mint(alice, AMOUNT);
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(RWAToken.NotRedeemer.selector, stranger));
        token.burnFrom(alice, 1 ether);
    }

    function test_BurnFrom_RevertsOnInsufficientBalance() public {
        _mint(alice, 5 ether);
        vm.prank(address(redemption));
        vm.expectRevert(
            abi.encodeWithSelector(RWAToken.InsufficientBalance.selector, alice, 5 ether, 6 ether)
        );
        token.burnFrom(alice, 6 ether);
    }

    /*//////////////////////////////////////////////////////////////
                                 FUZZ
    //////////////////////////////////////////////////////////////*/

    function testFuzz_Transfer_ConservesSupply(uint256 mintAmt, uint256 sendAmt) public {
        mintAmt = bound(mintAmt, 1, type(uint128).max);
        sendAmt = bound(sendAmt, 0, mintAmt);
        _mint(alice, mintAmt);
        vm.prank(alice);
        token.transfer(bob, sendAmt);
        assertEq(token.balanceOf(alice) + token.balanceOf(bob), mintAmt, "sum conserved");
        assertEq(token.totalSupply(), mintAmt, "supply conserved");
    }

    function testFuzz_Mint_RejectsUnverified(address to, uint256 amt) public {
        vm.assume(to != alice && to != bob && to != address(0));
        vm.assume(!identity.isVerified(to));
        amt = bound(amt, 1, type(uint128).max);
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(RWAToken.RecipientNotVerified.selector, to));
        token.mint(to, amt);
    }

    /*//////////////////////////////////////////////////////////////
                                 HELPERS
    //////////////////////////////////////////////////////////////*/

    function _freshToken() internal returns (RWAToken) {
        vm.prank(owner);
        return new RWAToken(TOKEN_NAME, TOKEN_SYMBOL, address(identity), owner);
    }
}
