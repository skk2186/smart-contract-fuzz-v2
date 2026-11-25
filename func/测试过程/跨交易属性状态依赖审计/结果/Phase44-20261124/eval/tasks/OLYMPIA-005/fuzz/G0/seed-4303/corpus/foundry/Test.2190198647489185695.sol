// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x50000);
    address constant USER5 = address(0x30000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x7f, 0xcf13);
    _setUpActor(USER1);
        Target.step();
        _delay(0x9, 0x13);
    _setUpActor(USER2);
        Target.step();
        _delay(0x85b27, 0x13);
    _setUpActor(USER1);
        Target.step();
        _delay(0x80772, 0x7fff);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5bd20, 0x95ce);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3e1ce, 0x12);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7d1b7, 0x5ef7);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4694f, 0xd8f2);
    _setUpActor(USER3);
        Target.step();
        _setUpActor(USER3);
        Target.step();
        _delay(0xb, 0x139a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1b, 0x2f15);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6c82f, 0x30cd);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb3c, 0x1392);
    _setUpActor(USER5);
        Target.step();
        _delay(0x582b0, 0x1392);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb38, 0x7a00);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eac7, 0x3c09);
    _setUpActor(USER1);
        Target.step();
        _delay(0x212f1, 0x16);
    _setUpActor(USER5);
        Target.step();
        _delay(0x12, 0x14);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb32, 0xeb6b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x62e05, 0x1385);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb2f, 0xbcb9);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6a9f7, 0x3c07);
    _setUpActor(USER4);
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
