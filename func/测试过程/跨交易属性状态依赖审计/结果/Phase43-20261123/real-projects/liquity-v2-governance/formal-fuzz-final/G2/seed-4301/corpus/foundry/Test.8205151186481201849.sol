// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x40000);

    // TODO: Replace with your actual contract instance
    CryticTester Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new CryticTester();
  }

  function test_replay() public {
        _delay(0x5e705, 0xc348);
    _setUpActor(USER1);
        Target.governance_depositLQTY(309485009821345068724781053);
        _delay(0x1003, 0x40e8);
    _setUpActor(USER1);
        Target.excludeArtifacts();
        _delay(0x4eb1c, 0x3a2);
    _setUpActor(USER3);
        Target.invariant_BI04();
        _delay(0x8414, 0x95a0);
    _setUpActor(USER1);
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
