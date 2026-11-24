// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x20000);
    address constant USER3 = address(0x30000);

    // TODO: Replace with your actual contract instance
    CryticTester Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new CryticTester();
  }

  function test_replay() public {
        _delay(0x191e7, 0x9d0);
    _setUpActor(USER2);
        Target.helper_deployInitiative();
        _delay(0x1443a, 0xdd42);
    _setUpActor(USER3);
        Target.invariant_GV01();
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
