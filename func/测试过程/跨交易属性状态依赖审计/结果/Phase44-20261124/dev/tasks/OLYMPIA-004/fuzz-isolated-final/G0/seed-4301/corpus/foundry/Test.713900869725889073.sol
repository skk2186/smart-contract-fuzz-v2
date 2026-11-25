// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x50000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x20000);
    address constant USER4 = address(0x40000);
    address constant USER5 = address(0x10000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x2c, 0x17);
    _setUpActor(USER1);
        Target.step();
        _delay(0x10978, 0x5b6b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2e, 0x5c65);
    _setUpActor(USER2);
        Target.step();
        _delay(0x712e3, 0x2ea6);
    _setUpActor(USER3);
        Target.step();
        _delay(0x63160, 0x139f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1051, 0x17);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb31, 0x2b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x12, 0x7);
    _setUpActor(USER4);
        Target.step();
        _delay(0x77bce, 0x8980);
    _setUpActor(USER1);
        Target.step();
        _delay(0x8, 0x28);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6d464, 0x1398);
    _setUpActor(USER3);
        Target.step();
        _delay(0x34db, 0x4674);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1051, 0x7);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6c82f, 0xd);
    _setUpActor(USER4);
        Target.step();
        _delay(0x214c8, 0x1a41);
    _setUpActor(USER3);
        Target.step();
        _delay(0x580b0, 0xb0cd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1b73c, 0x8ffb);
    _setUpActor(USER2);
        Target.step();
        _delay(0x85b27, 0x25cb);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8b070, 0x26c0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5, 0x1);
    _setUpActor(USER2);
        Target.step();
        _delay(0x19, 0xcf13);
    _setUpActor(USER2);
        Target.step();
        _delay(0x576ad, 0x1372);
    _setUpActor(USER5);
        Target.step();
        _delay(0x8f9df, 0x1396);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6002d, 0x2e);
    _setUpActor(USER3);
        Target.step();
        _delay(0x5caa0, 0x95ce);
    _setUpActor(USER1);
        Target.step();
        _delay(0x16, 0x138a);
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
