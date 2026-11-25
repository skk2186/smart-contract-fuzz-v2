// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x20000);
    address constant USER3 = address(0x50000);
    address constant USER4 = address(0x10000);
    address constant USER5 = address(0x30000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x8345, 0xea4d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7f, 0x7c0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x307c6, 0x5daa);
    _setUpActor(USER3);
        Target.step();
        _delay(0x580b0, 0xa);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1b2da, 0xb0cd);
    _setUpActor(USER3);
        Target.step();
        _delay(0x94ab, 0x7840);
    _setUpActor(USER3);
        Target.step();
        _delay(0x214ca, 0x9d0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x3256a, 0x1390);
    _setUpActor(USER4);
        Target.step();
        _delay(0xc247, 0x5);
    _setUpActor(USER1);
        Target.step();
        _delay(0x63160, 0x7fe1);
    _setUpActor(USER1);
        Target.step();
        _delay(0x22a8d, 0x1a41);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb2c, 0x110);
    _setUpActor(USER5);
        Target.step();
        _delay(0x15, 0xd1ae);
    _setUpActor(USER3);
        Target.step();
        _delay(0xb056, 0x3c07);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3c, 0x7fff);
    _setUpActor(USER1);
        Target.step();
        _delay(0x214ca, 0x185a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2621e, 0xebcc);
    _setUpActor(USER1);
        Target.step();
        _delay(0x51251, 0xdefe);
    _setUpActor(USER4);
        Target.step();
        _delay(0xa, 0x6);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1a, 0xd1ae);
    _setUpActor(USER4);
        Target.step();
        _delay(0xff, 0x26ee);
    _setUpActor(USER5);
        Target.step();
        _delay(0x1b2da, 0xeb6b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x15, 0x1388);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6a2ce, 0x2e32);
    _setUpActor(USER5);
        Target.step();
        _delay(0x12, 0x1388);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3, 0x9cf);
    _setUpActor(USER2);
        Target.step();
        _delay(0x8a317, 0x30cd);
    _setUpActor(USER3);
        Target.step();
        _delay(0x52bdb, 0x54f1);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb32, 0x67b3);
    _setUpActor(USER1);
        Target.step();
        _delay(0x3264b, 0x3e8d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x16, 0x1397);
    _setUpActor(USER1);
        Target.step();
        _delay(0x71cfa, 0x7630);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1b73c, 0x8);
    _setUpActor(USER2);
        Target.step();
        _delay(0x65679, 0x7630);
    _setUpActor(USER3);
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
