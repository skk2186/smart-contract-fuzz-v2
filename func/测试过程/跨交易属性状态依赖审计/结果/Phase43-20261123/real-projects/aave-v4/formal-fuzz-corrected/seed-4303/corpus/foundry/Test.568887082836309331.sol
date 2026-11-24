// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x20000);
    address constant USER3 = address(0x40000);

    // TODO: Replace with your actual contract instance
    CryticTester Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new CryticTester();
  }

  function test_replay() public {
        _setUpActor(USER1);
        Target.switch_oracle(431997);
        _setUpActor(USER1);
        Target.switch_spoke(115792089237316195423570985008687907853269984665640564039457584002913129639937);
        _delay(0x48a09, 0xb589);
    _setUpActor(USER2);
        Target.invariant_totalBorrowedLessThanSupplied_v2();
        _delay(0x4cdfc, 0x26);
    _setUpActor(USER3);
        Target.switch_oracle(91860656429130030436587749251170239521053385371708043452478164387874235123574);
        _delay(0x668ec, 0x1385);
    _setUpActor(USER1);
        Target.invariant_totalBorrowedLessThanSupplied_v1();
        _delay(0x46fe0, 0xcf08);
    _setUpActor(USER2);
        Target.setUp();
        _delay(0x29ec0, 0xd91f);
    _setUpActor(USER1);
        Target.switch_oracle(40000899228459159118727896435184787723957109979616617844953118579116969938965);
        _delay(0x64730, 0xd86f);
    _setUpActor(USER1);
        Target.invariant_canary();
  }

  function _setUpActor(address actor) internal {
      vm.startPrank(actor);
      // Add any additional actor setup here if needed
  }

  function _delay(uint256 timeInSeconds, uint256 numBlocks) internal {
      vm.warp(block.timestamp + timeInSeconds);
      vm.roll(block.number + numBlocks);
  }
}
