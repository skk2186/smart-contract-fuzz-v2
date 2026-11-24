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
        _delay(0x4eb09, 0x6405);
    _setUpActor(USER1);
        Target.invariant_GV01();
        _delay(0x7e6f9, 0x4222);
    _setUpActor(USER3);
        Target.governance_depositLQTY(12);
        _delay(0x2ea72, 0xda73);
    _setUpActor(USER1);
        Target.governance_claimForInitiative(18);
        _delay(0x437f3, 0xeb21);
    _setUpActor(USER2);
        Target.governance_allocateLQTY_clamped_single_initiative(237, 75976295642210076144911530296, 67189804723454693750406344321);
        _delay(0x46c13, 0xd8d3);
    _setUpActor(USER1);
        Target.invariant_BI04();
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
