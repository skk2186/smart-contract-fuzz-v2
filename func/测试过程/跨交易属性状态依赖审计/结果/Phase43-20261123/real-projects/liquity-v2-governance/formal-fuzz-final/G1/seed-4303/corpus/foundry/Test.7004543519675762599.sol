// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x10000);

    // TODO: Replace with your actual contract instance
    CryticTester Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new CryticTester();
  }

  function test_replay() public {
        _delay(0x18b70, 0xbe36);
    _setUpActor(USER1);
        Target.invariant_BI05();
        _delay(0x1fffd, 0x8a09);
    _setUpActor(USER2);
        Target.helper_accrueBold(155989120312692930330789563);
        _delay(0x15149, 0x9bda);
    _setUpActor(USER1);
        Target.invariant_BI05();
        _delay(0x4fad7, 0xbb);
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
