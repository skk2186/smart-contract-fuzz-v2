// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x20000);

    // TODO: Replace with your actual contract instance
    CryticTester Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new CryticTester();
  }

  function test_replay() public {
        _delay(0x3e6, 0x364);
    _setUpActor(USER1);
        Target.invariant_GV01();
        _delay(0x7a2d7, 0x13a5);
    _setUpActor(USER2);
        Target.governance_depositLQTY(45);
        _delay(0x2eb49, 0x9ea2);
    _setUpActor(USER3);
        Target.invariant_BI04();
        _delay(0x4ea5e, 0xbaff);
    _setUpActor(USER4);
        Target.governance_withdrawLQTY(17);
        _delay(0x3c1a5, 0x5dab);
    _setUpActor(USER2);
        Target.governance_claimFromStakingV1(68);
        _delay(0x46736, 0x2f1b);
    _setUpActor(USER1);
        Target.governance_allocateLQTY_clamped_single_initiative(129, 28108767636977447597864120561, 32969800911193261782534490700);
        _delay(0x668ee, 0xb44c);
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
