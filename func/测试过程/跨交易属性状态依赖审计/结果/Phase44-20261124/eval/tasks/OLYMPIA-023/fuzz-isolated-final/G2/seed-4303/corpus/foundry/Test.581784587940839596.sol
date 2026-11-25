// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x30000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x50000);
    address constant USER4 = address(0x10000);
    address constant USER5 = address(0x20000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x5caa0, 0x2422);
    _setUpActor(USER1);
        Target.step();
        _delay(0x76ea6, 0x2e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb33, 0x20);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4, 0x20ff);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8a578, 0x16);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb32, 0x27);
    _setUpActor(USER4);
        Target.step();
        _setUpActor(USER3);
        Target.step();
        _delay(0x863e6, 0x4eb4);
    _setUpActor(USER2);
        Target.step();
        _delay(0x52be8, 0x9cf);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3e1ce, 0x1320);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6633e, 0x5d4d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x64ad5, 0x19);
    _setUpActor(USER4);
        Target.step();
        _delay(0x77bd0, 0x14);
    _setUpActor(USER5);
        Target.step();
        _delay(0x329b9, 0xeb6b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x77bd0, 0x47fd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb2e, 0x139b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x8f9df, 0x1373);
    _setUpActor(USER4);
        Target.step();
        _delay(0xffff, 0x95ce);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eac7, 0x8ffb);
    _setUpActor(USER3);
        Target.step();
        _delay(0x214c9, 0x5caa);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1f113, 0x138f);
    _setUpActor(USER2);
        Target.step();
        _delay(0x85b27, 0x1379);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb3f, 0x7a00);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8, 0x89b0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x7d1b7, 0xff);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb19, 0x5db9);
    _setUpActor(USER4);
        Target.step();
        _delay(0x214c8, 0xe8a0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x80772, 0x552);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2c, 0x14);
    _setUpActor(USER1);
        Target.step();
        _delay(0xa, 0xd13a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x329b9, 0xbaad);
    _setUpActor(USER5);
        Target.step();
        _delay(0x576ad, 0xc543);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb3b, 0xebcc);
    _setUpActor(USER5);
        Target.step();
        _setUpActor(USER4);
        Target.step();
        _delay(0x1c18d, 0xb31c);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb45, 0x13bd);
    _setUpActor(USER5);
        Target.step();
        _delay(0x580b0, 0x9de);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7f467, 0xea4f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7f7c2, 0x7c0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x64ad5, 0xd0cb);
    _setUpActor(USER3);
        Target.step();
        _delay(0x82491, 0x5caa);
    _setUpActor(USER1);
        Target.step();
        _delay(0x212f1, 0x1397);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2, 0x89b0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6d828, 0x1391);
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
