// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x50000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x20000);
    address constant USER5 = address(0x30000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x7eea7, 0xeb58);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7eea7, 0x992a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x76ea6, 0x4f13);
    _setUpActor(USER3);
        Target.step();
        _delay(0x65679, 0x3ed9);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb32, 0xeb58);
    _setUpActor(USER4);
        Target.step();
        _delay(0x475d0, 0x138b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x433c2, 0x26c0);
    _setUpActor(USER5);
        Target.step();
        _delay(0xb, 0x13);
    _setUpActor(USER2);
        Target.step();
        _delay(0x7d1b7, 0xb7e3);
    _setUpActor(USER1);
        Target.step();
        _delay(0x118c2, 0x5);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2c, 0x20ff);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5bd20, 0x2f15);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6123, 0x87a0);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6d3ce, 0x2e81);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb30, 0x7a00);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb34, 0x138a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8af1a, 0x7840);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6, 0xb0cd);
    _setUpActor(USER2);
        Target.step();
        vm.stopPrank();
        vm.prank(address(0x10000));
        assertFalse(Target.echidna_noBug());
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
