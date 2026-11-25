// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x30000);
    address constant USER2 = address(0x20000);
    address constant USER3 = address(0x40000);
    address constant USER4 = address(0x10000);
    address constant USER5 = address(0x50000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x15, 0x13bd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x580b0, 0xc543);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3, 0x1397);
    _setUpActor(USER3);
        Target.step();
        _delay(0x63720, 0x28);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7f7c2, 0xea96);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb38, 0x1390);
    _setUpActor(USER3);
        Target.step();
        _delay(0x804a4, 0x1386);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb20, 0xb31c);
    _setUpActor(USER2);
        Target.step();
        _delay(0x28, 0xd13a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6b504, 0x2e81);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2a, 0x1386);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4, 0x13be);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2, 0x1372);
    _setUpActor(USER3);
        Target.step();
        _delay(0x2a, 0x9376);
    _setUpActor(USER2);
        Target.step();
        _delay(0x28, 0x5c65);
    _setUpActor(USER1);
        Target.step();
        _delay(0x214c8, 0x94d4);
    _setUpActor(USER1);
        Target.step();
        _delay(0x582b0, 0x1394);
    _setUpActor(USER5);
        Target.step();
        _delay(0x11d50, 0xb9f8);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7f, 0xe1e3);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6c82f, 0x139b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x13, 0x5daa);
    _setUpActor(USER5);
        Target.step();
        _delay(0x64ad5, 0x13);
    _setUpActor(USER1);
        Target.step();
        _delay(0x875e1, 0x1387);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb45, 0x9052);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5408b, 0xd065);
    _setUpActor(USER3);
        Target.step();
        _delay(0x214c8, 0x1320);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3a, 0x552);
    _setUpActor(USER1);
        Target.step();
        _delay(0x10, 0x1378);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5, 0x2f7b);
    _setUpActor(USER2);
        Target.step();
        _delay(0xc247, 0x1391);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1f113, 0x7c0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb1a, 0xb);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6ae4e, 0x3a9d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x10978, 0x2b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x15b9d, 0x5c65);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8a317, 0x4ddd);
    _setUpActor(USER5);
        Target.step();
        _delay(0x189e3, 0x1390);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5caa0, 0x5ef7);
    _setUpActor(USER3);
        Target.step();
        _delay(0x28d57, 0xea4f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x63160, 0xc107);
    _setUpActor(USER1);
        Target.step();
        _delay(0x189e3, 0x3);
    _setUpActor(USER3);
        Target.step();
        _delay(0x10, 0x20);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb39, 0x27);
    _setUpActor(USER5);
        Target.step();
        _delay(0x712e4, 0x2d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x712e4, 0x2);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7d1b7, 0x17);
    _setUpActor(USER4);
        Target.step();
        _delay(0x53a0f, 0x9de);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb37, 0xd38b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3d, 0xb556);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb30, 0x1392);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7, 0x29);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6356a, 0xd065);
    _setUpActor(USER4);
        Target.step();
        _delay(0x10, 0x619b);
    _setUpActor(USER5);
        Target.step();
        _delay(0xd, 0x16);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2621e, 0x1398);
    _setUpActor(USER2);
        Target.step();
        _delay(0x668ee, 0x4f13);
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
