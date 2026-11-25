// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x20000);
    address constant USER3 = address(0x30000);
    address constant USER4 = address(0x40000);
    address constant USER5 = address(0x50000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x875e1, 0xd619);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7f7c2, 0xa);
    _setUpActor(USER2);
        Target.step();
        _delay(0x41a2, 0x2f15);
    _setUpActor(USER2);
        Target.step();
        _delay(0x42655, 0x13bd);
    _setUpActor(USER3);
        Target.step();
        _delay(0x94ab, 0x1385);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4c3f3, 0xc543);
    _setUpActor(USER5);
        Target.step();
        _delay(0x11, 0x7630);
    _setUpActor(USER2);
        Target.step();
        _delay(0x67888, 0x7a00);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb3f, 0xd13a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x582b0, 0x6);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6c82f, 0x7a00);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7f, 0x1475);
    _setUpActor(USER2);
        Target.step();
        _delay(0x214c9, 0x2ea6);
    _setUpActor(USER4);
        Target.step();
        _delay(0x77bce, 0x116e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1, 0x755a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x94ab, 0x1397);
    _setUpActor(USER3);
        Target.step();
        _delay(0x77bce, 0xa4f5);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4daf5, 0x2c55);
    _setUpActor(USER3);
        Target.step();
        _delay(0xc4f1, 0x3a9d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x189e3, 0x320);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb34, 0xea4f);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2621e, 0xb556);
    _setUpActor(USER5);
        Target.step();
        _delay(0x1b73c, 0x7630);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6, 0x7840);
    _setUpActor(USER2);
        Target.step();
        _delay(0x85b27, 0xd0cb);
    _setUpActor(USER1);
        Target.step();
        _delay(0x103ef, 0x6b0c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4a55, 0x1a41);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7eea7, 0xb556);
    _setUpActor(USER2);
        Target.step();
        _delay(0x142f0, 0xb2fb);
    _setUpActor(USER4);
        Target.step();
        _delay(0x433c2, 0x47fd);
    _setUpActor(USER4);
        Target.step();
        _delay(0x5408b, 0x1389);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1b73c, 0x1c9b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x875e1, 0x30cd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x41a2, 0xb);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6d828, 0xd);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4, 0x47fd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x42655, 0x30cd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2621e, 0x1397);
    _setUpActor(USER5);
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
