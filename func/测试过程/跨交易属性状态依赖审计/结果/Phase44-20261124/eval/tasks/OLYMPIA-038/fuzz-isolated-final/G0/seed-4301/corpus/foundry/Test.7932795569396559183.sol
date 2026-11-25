// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x50000);
    address constant USER2 = address(0x20000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x40000);
    address constant USER5 = address(0x30000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eb45, 0x1378);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb25, 0x1373);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4ecff, 0xb31c);
    _setUpActor(USER2);
        Target.step();
        _delay(0x37272, 0x87a0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x668ee, 0x2f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6ae4e, 0xe8a0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5d, 0x3b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x26, 0x1389);
    _setUpActor(USER4);
        Target.step();
        _delay(0x712e4, 0x1a);
    _setUpActor(USER5);
        Target.step();
        _delay(0x25f69, 0xea4d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb42, 0x56);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3e1ce, 0x47);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb16, 0x43);
    _setUpActor(USER5);
        Target.step();
        _delay(0x712e3, 0x39);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4a55, 0x26);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb23, 0x3c);
    _setUpActor(USER5);
        Target.step();
        _delay(0x65410, 0xe4d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x433c2, 0xf);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eaf5, 0x1320);
    _setUpActor(USER2);
        Target.step();
        _delay(0x56, 0x137a);
    _setUpActor(USER5);
        Target.step();
        _delay(0x3a, 0x1394);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb23, 0x26ee);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb3a, 0x4069);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eafe, 0x3d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2d, 0x7c0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x3c500, 0x3a03);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1f113, 0x20);
    _setUpActor(USER5);
        Target.step();
        _delay(0x3644a, 0x47);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eaf4, 0x552);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6c82f, 0xb31c);
    _setUpActor(USER2);
        Target.step();
        _delay(0x28928, 0x1347);
    _setUpActor(USER1);
        Target.step();
        _delay(0x189e3, 0x1380);
    _setUpActor(USER5);
        Target.step();
        _delay(0x62123, 0x4e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4df30, 0x1475);
    _setUpActor(USER1);
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
