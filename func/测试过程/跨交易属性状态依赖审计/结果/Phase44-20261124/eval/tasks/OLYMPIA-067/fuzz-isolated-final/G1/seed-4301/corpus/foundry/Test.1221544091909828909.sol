// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x50000);
    address constant USER3 = address(0x30000);
    address constant USER4 = address(0x10000);
    address constant USER5 = address(0x20000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x3d, 0xb0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7d, 0x10);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3, 0x3c09);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4ea94, 0x781e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4ea68, 0x12d8);
    _setUpActor(USER2);
        Target.step();
        _delay(0x64, 0xcb);
    _setUpActor(USER1);
        Target.step();
        _delay(0x11, 0xd1);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4ea67, 0x1300);
    _setUpActor(USER4);
        Target.step();
        _delay(0x42, 0x1388);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4ea8c, 0x5c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4ea68, 0x12d7);
    _setUpActor(USER1);
        Target.step();
        _delay(0x214ca, 0x12d5);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb25, 0x17df);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb10, 0x7d8c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x72, 0x1356);
    _setUpActor(USER3);
        Target.step();
        _delay(0xd4, 0x12f7);
    _setUpActor(USER1);
        Target.step();
        _delay(0xc4, 0x2);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eac8, 0xd3);
    _setUpActor(USER4);
        Target.step();
        _delay(0xc5, 0x30cd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4ea7f, 0x16);
    _setUpActor(USER4);
        Target.step();
        _delay(0xb7, 0x12db);
    _setUpActor(USER3);
        Target.step();
        _delay(0x24e8, 0x134d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6a, 0x928a);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4d450, 0x12);
    _setUpActor(USER4);
        Target.step();
        _delay(0xa5, 0x1328);
    _setUpActor(USER1);
        Target.step();
        _delay(0x9f, 0x12f5);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eab1, 0x139a);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4ea97, 0x9);
    _setUpActor(USER1);
        Target.step();
        _delay(0x712e4, 0x1366);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8345, 0xd38b);
    _setUpActor(USER3);
        Target.step();
        _delay(0xd9, 0x7e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb38, 0x12ce);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb17, 0xbe);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb28, 0xde);
    _setUpActor(USER5);
        Target.step();
        _delay(0xb9, 0x7);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb04, 0x1360);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4d, 0x137f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3f, 0x1353);
    _setUpActor(USER3);
        Target.step();
        _delay(0x69, 0x4);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7cf4e, 0x12c3);
    _setUpActor(USER1);
        Target.step();
        _delay(0x57, 0x1370);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4ea8f, 0x7840);
    _setUpActor(USER2);
        Target.step();
        _delay(0x71bac, 0x116e);
    _setUpActor(USER1);
        Target.step();
        _delay(0x9b, 0xc2);
    _setUpActor(USER5);
        Target.step();
        _delay(0x556c4, 0x94);
    _setUpActor(USER2);
        Target.step();
        _delay(0x11d50, 0x9c);
    _setUpActor(USER4);
        Target.step();
        _delay(0xd7, 0x8);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4ea79, 0x37);
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
