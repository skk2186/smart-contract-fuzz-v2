// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x30000);

    // TODO: Replace with your actual contract instance
    CryticTester Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new CryticTester();
  }

  function test_replay() public {
        _delay(0x29382, 0xc34b);
    _setUpActor(USER1);
        Target.governance_depositLQTY(309485009821345068724781053);
        _delay(0x2621e, 0x8ecb);
    _setUpActor(USER1);
        Target.invariant_BI03();
        _delay(0xe8b4, 0x7148);
    _setUpActor(USER3);
        Target.invariant_GV01();
        _delay(0x52e10, 0xfba);
    _setUpActor(USER3);
        Target.governance_allocateLQTY_clamped_single_initiative(25, 3570988007, 0);
        _delay(0x7492a, 0x7c1);
    _setUpActor(USER4);
        Target.invariant_BI04();
        _delay(0x46c12, 0x1210);
    _setUpActor(USER1);
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
