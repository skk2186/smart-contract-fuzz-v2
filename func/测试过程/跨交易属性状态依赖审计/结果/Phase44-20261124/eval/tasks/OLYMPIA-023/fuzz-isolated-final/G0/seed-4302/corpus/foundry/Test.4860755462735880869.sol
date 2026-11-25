// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x30000);
    address constant USER2 = address(0x50000);
    address constant USER3 = address(0x40000);
    address constant USER4 = address(0x10000);
    address constant USER5 = address(0x20000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x6c82f, 0x30cd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1f113, 0x597d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1051, 0x1375);
    _setUpActor(USER2);
        Target.step();
        _delay(0xd, 0x1373);
    _setUpActor(USER3);
        Target.step();
        _delay(0x24b01, 0xea4e);
    _setUpActor(USER3);
        Target.step();
        _delay(0x13, 0x6);
    _setUpActor(USER1);
        Target.step();
        _delay(0x3, 0x9);
    _setUpActor(USER3);
        Target.step();
        _delay(0x16, 0x7630);
    _setUpActor(USER1);
        Target.step();
        _delay(0x65410, 0x10);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb32, 0x7e62);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4694f, 0x2e81);
    _setUpActor(USER4);
        Target.step();
        _delay(0x14, 0x16);
    _setUpActor(USER1);
        Target.step();
        _delay(0x65410, 0x89b0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x77bce, 0x1399);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1f113, 0x138b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb39, 0x1390);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3340a, 0xd065);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eac7, 0x6b0c);
    _setUpActor(USER1);
        Target.step();
        _delay(0x10, 0x9c1);
    _setUpActor(USER2);
        Target.step();
        _delay(0x7f7c2, 0x12);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6b504, 0x4963);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4a0f1, 0x1391);
    _setUpActor(USER2);
        Target.step();
        _delay(0x37272, 0x8);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1b, 0x552);
    _setUpActor(USER2);
        Target.step();
        _delay(0x804a4, 0xd47c);
    _setUpActor(USER5);
        Target.step();
        _delay(0x63720, 0xc);
    _setUpActor(USER2);
        Target.step();
        _delay(0x11d50, 0xd);
    _setUpActor(USER3);
        Target.step();
        _delay(0x712e4, 0x1c9b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x668ee, 0x6b0c);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb3c, 0x2e);
    _setUpActor(USER1);
        Target.step();
        _delay(0x8a317, 0x47fd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1b73c, 0x8);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3, 0x1f0e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1a, 0x231);
    _setUpActor(USER2);
        Target.step();
        _delay(0x66815, 0x8f33);
    _setUpActor(USER2);
        Target.step();
        _delay(0x46b47, 0xc5);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb1b, 0x4f13);
    _setUpActor(USER4);
        Target.step();
        _delay(0x475d0, 0xd065);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3a, 0x28);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2f, 0x84e4);
    _setUpActor(USER4);
        Target.step();
        _delay(0x29, 0xd88a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6a9f7, 0x2f15);
    _setUpActor(USER3);
        Target.step();
        _delay(0x2fa33, 0x139e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x580b0, 0x1379);
    _setUpActor(USER5);
        Target.step();
        _delay(0xc4f1, 0xc543);
    _setUpActor(USER2);
        Target.step();
        _delay(0x16e1, 0x1376);
    _setUpActor(USER5);
        Target.step();
        _delay(0x329b9, 0x1389);
    _setUpActor(USER4);
        Target.step();
        _delay(0xd, 0x58ab);
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
