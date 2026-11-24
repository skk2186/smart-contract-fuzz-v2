// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x20000);
    address constant USER4 = address(0x40000);

    // TODO: Replace with your actual contract instance
    CryticTester Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new CryticTester();
  }

  function test_replay() public {
        _delay(0x29385, 0xddd3);
    _setUpActor(USER1);
        Target.governance_depositLQTY(25706484659139486004319433);
        _delay(0x580b0, 0xda73);
    _setUpActor(USER2);
        Target.governance_snapshotVotesForInitiative(address(0xee35211c4d9126d520bbfeaf3cfee5fe7b86f221));
        _delay(0x2bf47, 0xc9c);
    _setUpActor(USER3);
        Target.invariant_BI03();
        _delay(0x7f0c6, 0x2739);
    _setUpActor(USER1);
        Target.invariant_BI05();
        _delay(0x875e5, 0xad65);
    _setUpActor(USER4);
        Target.governance_depositLQTY(45);
        _delay(0x7a11d, 0xa22d);
    _setUpActor(USER3);
        Target.governance_allocateLQTY_clamped_single_initiative(0, 0, 68582632910623741080708738347);
        _delay(0xb768, 0x1d19);
    _setUpActor(USER2);
        Target.governance_snapshotVotesForInitiative(address(0x2fffffffd));
        _delay(0x2bf45, 0xa882);
    _setUpActor(USER2);
        Target.invariant_BI03();
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
