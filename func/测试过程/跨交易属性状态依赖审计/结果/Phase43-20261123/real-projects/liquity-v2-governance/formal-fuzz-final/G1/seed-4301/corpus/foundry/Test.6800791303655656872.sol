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
        _delay(0x3b4d4, 0xa14a);
    _setUpActor(USER1);
        Target.governance_claimForInitiative(104);
        _delay(0x2ef18, 0x231);
    _setUpActor(USER2);
        Target.governance_depositLQTY(6359979740066385395820796);
        _delay(0x210a8, 0x53bf);
    _setUpActor(USER3);
        Target.governance_depositLQTY(918309064);
        _delay(0x6f3b6, 0x12b6);
    _setUpActor(USER3);
        Target.assert_canary_ASSERTION_CANARY(115792089237316195423570985008687907853269984665640564039455584007913129639938);
        _delay(0x11d53, 0x2971);
    _setUpActor(USER2);
        Target.governance_allocateLQTY_clamped_single_initiative(3, 17991324341463245467058004902, 0);
        _delay(0x3b5a9, 0x9235);
    _setUpActor(USER4);
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
