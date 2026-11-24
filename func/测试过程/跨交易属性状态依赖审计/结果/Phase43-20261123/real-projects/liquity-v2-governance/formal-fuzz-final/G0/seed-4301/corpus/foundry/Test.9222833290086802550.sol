// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x30000);
    address constant USER2 = address(0x10000);
    address constant USER3 = address(0x20000);

    // TODO: Replace with your actual contract instance
    CryticTester Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new CryticTester();
  }

  function test_replay() public {
        _delay(0x3b4d4, 0xa14a);
    _setUpActor(USER1);
        Target.governance_claimForInitiative(104);
        _delay(0x6f400, 0x101d);
    _setUpActor(USER2);
        Target.governance_snapshotVotesForInitiative(address(0xa329c0648769a73afac7f9381e08fb43dbea72));
        _delay(0xeb49, 0x5e9d);
    _setUpActor(USER3);
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
