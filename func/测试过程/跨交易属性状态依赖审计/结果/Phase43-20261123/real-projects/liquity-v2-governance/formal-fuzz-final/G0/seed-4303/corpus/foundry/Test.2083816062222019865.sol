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
        _delay(0x650bd, 0xc77f);
    _setUpActor(USER2);
        Target.governance_snapshotVotesForInitiative(address(0xbeef));
        _delay(0x36c1c, 0xcfae);
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
