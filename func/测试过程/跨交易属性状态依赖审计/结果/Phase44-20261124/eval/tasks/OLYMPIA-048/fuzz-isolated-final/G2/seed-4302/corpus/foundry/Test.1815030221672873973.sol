// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x10000);
    address constant USER3 = address(0x50000);
    address constant USER4 = address(0x20000);
    address constant USER5 = address(0x30000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x40, 0x1347);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6a9f7, 0x4a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x36, 0x31);
    _setUpActor(USER2);
        Target.step();
        _delay(0x576ad, 0x136c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaea, 0xd8f2);
    _setUpActor(USER4);
        Target.step();
        _delay(0x21, 0x37);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb36, 0x6b0c);
    _setUpActor(USER2);
        Target.step();
        _delay(0x27, 0xc18d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb22, 0x134d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x65410, 0x64);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7db13, 0x1351);
    _setUpActor(USER4);
        Target.step();
        _delay(0xff, 0x134b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x47aef, 0x1378);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2e, 0x2e32);
    _setUpActor(USER4);
        Target.step();
        _delay(0x36, 0x87a0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb0d, 0x5ef7);
    _setUpActor(USER3);
        Target.step();
        _delay(0x5, 0x135b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6a9f7, 0x1c);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb14, 0x1393);
    _setUpActor(USER2);
        Target.step();
        _delay(0x40, 0xea96);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb38, 0x138f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3b, 0x135e);
    _setUpActor(USER5);
        Target.step();
        _delay(0x41a2, 0x3a);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4a0f1, 0x1377);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2c, 0x97ba);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1051, 0x2f15);
    _setUpActor(USER1);
        Target.step();
        _delay(0xc, 0x1374);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eae4, 0xea96);
    _setUpActor(USER3);
        Target.step();
        _delay(0x63160, 0x3e8f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x77bd0, 0x4b64);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb11, 0x33);
    _setUpActor(USER5);
        Target.step();
        _setUpActor(USER4);
        Target.step();
        _delay(0x433c2, 0x7317);
    _setUpActor(USER2);
        Target.step();
        _delay(0x73121, 0x1b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x59, 0xc04);
    _setUpActor(USER1);
        Target.step();
        _delay(0x9dee, 0x138d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb23, 0x40);
    _setUpActor(USER2);
        Target.step();
        _delay(0x8f9df, 0x139a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x51251, 0x13bd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb10, 0x2f7b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5b, 0x134b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eac7, 0x9d0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x28, 0x1355);
    _setUpActor(USER2);
        Target.step();
        _delay(0x34, 0xd1ae);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb21, 0x28);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3a, 0x3a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x63160, 0x2c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3b, 0x87a0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb04, 0x21);
    _setUpActor(USER4);
        Target.step();
        _delay(0xf, 0x1357);
    _setUpActor(USER4);
        Target.step();
        _delay(0x5e, 0x1357);
    _setUpActor(USER3);
        Target.step();
        _delay(0x57, 0x5caa);
    _setUpActor(USER1);
        Target.step();
        _delay(0x36, 0x134e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eae5, 0x39);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb33, 0x2d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb44, 0x5d6f);
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
