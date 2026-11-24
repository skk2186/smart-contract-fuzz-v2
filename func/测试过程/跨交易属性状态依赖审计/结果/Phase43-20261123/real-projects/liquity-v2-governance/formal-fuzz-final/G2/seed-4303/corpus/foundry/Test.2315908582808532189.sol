// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x30000);

    // TODO: Replace with your actual contract instance
    CryticTester Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new CryticTester();
  }

  function test_replay() public {
        _delay(0x1d, 0x9a29);
    _setUpActor(USER1);
        Target.helper_accrueBold(67722722458419323914503345);
        _delay(0x1425f, 0xba);
    _setUpActor(USER1);
        Target.invariant_BI01();
        _delay(0x498d0, 0x5fb4);
    _setUpActor(USER2);
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
