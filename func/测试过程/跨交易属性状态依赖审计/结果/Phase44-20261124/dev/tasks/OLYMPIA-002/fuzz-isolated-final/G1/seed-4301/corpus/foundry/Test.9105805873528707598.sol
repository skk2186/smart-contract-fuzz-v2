// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x30000);
    address constant USER4 = address(0x50000);
    address constant USER5 = address(0x10000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eb32, 0x3ed9);
    _setUpActor(USER2);
        Target.step();
        _delay(0x63720, 0x18);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3c, 0xe8a0);
    _setUpActor(USER4);
        Target.step();
        _delay(0x10978, 0x138d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x13, 0xd065);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7eea7, 0xd13a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x62123, 0xd0cb);
    _setUpActor(USER1);
        Target.step();
        _delay(0x214ca, 0x79dd);
    _setUpActor(USER4);
        Target.step();
        _delay(0x77bd0, 0x8980);
    _setUpActor(USER1);
        Target.step();
        _delay(0xffff, 0x4ddd);
    _setUpActor(USER5);
        Target.step();
        _delay(0x74d9f, 0xe59f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x189e3, 0xc107);
    _setUpActor(USER4);
        Target.step();
        _delay(0x433c2, 0x138f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x214c9, 0x320);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6ae4e, 0x231);
    _setUpActor(USER5);
        Target.step();
        _delay(0x41a2, 0x1386);
    _setUpActor(USER1);
        Target.step();
        _delay(0xb, 0x1394);
    _setUpActor(USER3);
        Target.step();
        _delay(0x189e3, 0x139a);
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
