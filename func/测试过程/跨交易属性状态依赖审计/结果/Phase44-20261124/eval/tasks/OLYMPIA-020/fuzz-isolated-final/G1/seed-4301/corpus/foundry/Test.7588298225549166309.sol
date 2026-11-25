// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x50000);
    address constant USER4 = address(0x40000);
    address constant USER5 = address(0x10000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x214c9, 0x9cf7);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2, 0x1388);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6a2ce, 0xd619);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5387a, 0x1398);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb42, 0xc9f8);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb30, 0x7);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb36, 0x2f15);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1b2da, 0x3ed9);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6a9f7, 0x54a2);
    _setUpActor(USER2);
        Target.step();
        _delay(0x576ad, 0x2f7b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5caa0, 0xea4e);
    _setUpActor(USER1);
        Target.step();
        _delay(0x66815, 0xcf13);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7cf4e, 0x1385);
    _setUpActor(USER3);
        Target.step();
        _delay(0xca44, 0xe4d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x37fc9, 0x26ee);
    _setUpActor(USER4);
        Target.step();
        _delay(0x582b0, 0xc107);
    _setUpActor(USER5);
        Target.step();
        _delay(0x94ab, 0xd1ae);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8e1d1, 0x85e0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x1a18d, 0x1390);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6a2ce, 0x89b0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x42655, 0x85e0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x94ab, 0x14);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5, 0x4971);
    _setUpActor(USER3);
        Target.step();
        _delay(0xc247, 0xa663);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2, 0x5ef7);
    _setUpActor(USER2);
        Target.step();
        _delay(0x214c9, 0xaa10);
    _setUpActor(USER4);
        Target.step();
        _delay(0xb, 0x3);
    _setUpActor(USER3);
        Target.step();
        _delay(0x63160, 0x7840);
    _setUpActor(USER2);
        Target.step();
        _delay(0x189e3, 0x619b);
    _setUpActor(USER2);
        Target.step();
        _delay(0xa, 0x440);
    _setUpActor(USER4);
        Target.step();
        _delay(0x10978, 0x17);
    _setUpActor(USER1);
        Target.step();
        _delay(0x8af1a, 0x85e0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4694f, 0xe);
    _setUpActor(USER1);
        Target.step();
        _delay(0x712e4, 0x8980);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5bd20, 0x139f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb32, 0x3c08);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb2e, 0x753b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x14, 0x10);
    _setUpActor(USER4);
        Target.step();
        _delay(0x475d0, 0x10);
    _setUpActor(USER2);
        Target.step();
        _delay(0xc247, 0x7a00);
    _setUpActor(USER1);
        Target.step();
        _delay(0x8, 0x2f15);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6b721, 0x4f3b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6a2ce, 0x8980);
    _setUpActor(USER5);
        Target.step();
        _delay(0x2621e, 0x2e81);
    _setUpActor(USER3);
        Target.step();
        _delay(0x41a2, 0x1b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x42655, 0xea4d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7eea7, 0x5aeb);
    _setUpActor(USER2);
        Target.step();
        _delay(0x189e3, 0xd065);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb43, 0x138d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x189e3, 0x1414);
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
