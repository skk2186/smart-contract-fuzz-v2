// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x30000);
    address constant USER2 = address(0x10000);
    address constant USER3 = address(0x40000);
    address constant USER4 = address(0x20000);

    // TODO: Replace with your actual contract instance
    CryticTester Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new CryticTester();
  }

  function test_replay() public {
        _delay(0x78, 0x460);
    _setUpActor(USER1);
        Target.invariant_BI03();
        _delay(0x160cd, 0x3f51);
    _setUpActor(USER2);
        Target.invariant_BI04();
        _delay(0x6a9f7, 0x16a0);
    _setUpActor(USER2);
        Target.helper_deployInitiative();
        _delay(0x33e5b, 0xdfdf);
    _setUpActor(USER4);
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
