// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x30000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x20000);

    // TODO: Replace with your actual contract instance
    CryticTester Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new CryticTester();
  }

  function test_replay() public {
        _delay(0x7da25, 0xd936);
    _setUpActor(USER1);
        Target.invariant_hubAddedSharesMatchesSpokeSum();
        _delay(0x30b2f, 0x241d);
    _setUpActor(USER2);
        Target.switch_spoke(58718547945333826566591735050958066969432221831083240605806599228144739169716);
        _delay(0x26a9, 0xbe46);
    _setUpActor(USER3);
        Target.assert_canary_ASSERTION_CANARY(0);
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
