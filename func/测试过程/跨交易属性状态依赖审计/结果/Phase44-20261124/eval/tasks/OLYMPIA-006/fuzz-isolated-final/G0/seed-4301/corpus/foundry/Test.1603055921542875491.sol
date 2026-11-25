// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x30000);
    address constant USER4 = address(0x20000);
    address constant USER5 = address(0x50000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eb3d, 0x28);
    _setUpActor(USER1);
        Target.step();
        _delay(0x103ef, 0x1386);
    _setUpActor(USER2);
        Target.step();
        _delay(0x28, 0x47fd);
    _setUpActor(USER3);
        Target.step();
        _delay(0x24b01, 0x1397);
    _setUpActor(USER4);
        Target.step();
        _delay(0x55996, 0x3ed9);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb40, 0x5c65);
    _setUpActor(USER2);
        Target.step();
        _delay(0x28928, 0x138a);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6c82f, 0x7a00);
    _setUpActor(USER2);
        Target.step();
        _delay(0x65373, 0xd38b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x64ad5, 0x231);
    _setUpActor(USER4);
        Target.step();
        _delay(0x712e4, 0x139b);
    _setUpActor(USER1);
        Target.step();
        _delay(0xffff, 0x1a41);
    _setUpActor(USER4);
        Target.step();
        _delay(0x75d98, 0x1387);
    _setUpActor(USER1);
        Target.step();
        _delay(0xf, 0x1);
    _setUpActor(USER4);
        Target.step();
        _delay(0x65410, 0x1c9b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x11d50, 0x138c);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2f, 0x2b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3f4f4, 0xc);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb2c, 0x13);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb1b, 0x4);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1b73c, 0x17);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2621e, 0x116e);
    _setUpActor(USER3);
        Target.step();
        _delay(0x142ee, 0x139f);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4a0f1, 0x9d0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x748b4, 0x13);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2d, 0x440);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb45, 0x9de);
    _setUpActor(USER5);
        Target.step();
        _delay(0x875e1, 0x2e32);
    _setUpActor(USER3);
        Target.step();
        _delay(0x212f1, 0xb556);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb1d, 0x9de);
    _setUpActor(USER1);
        Target.step();
        _delay(0x329b9, 0x13);
    _setUpActor(USER5);
        Target.step();
        _delay(0x80772, 0x1);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb2e, 0x2ea6);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5bd20, 0x1475);
    _setUpActor(USER1);
        Target.step();
        _delay(0x99bf, 0x26ee);
    _setUpActor(USER5);
        Target.step();
        _delay(0xa015, 0x7);
    _setUpActor(USER2);
        Target.step();
        _delay(0x63160, 0x9d0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x80772, 0xea4f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb3f, 0x3c07);
    _setUpActor(USER5);
        Target.step();
        _delay(0x214ca, 0x26ee);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2d, 0xcf13);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5caa0, 0x12);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb42, 0x139b);
    _setUpActor(USER3);
        Target.step();
        _delay(0xb056, 0x139f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb2c, 0x1374);
    _setUpActor(USER3);
        Target.step();
        _delay(0xc4f1, 0x20ff);
    _setUpActor(USER1);
        Target.step();
        _delay(0x74d9f, 0x1396);
    _setUpActor(USER4);
        Target.step();
        _delay(0x9, 0xb);
    _setUpActor(USER5);
        Target.step();
        _delay(0x62e05, 0x2d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb31, 0xeb58);
    _setUpActor(USER5);
        Target.step();
        _delay(0x3, 0x7fe1);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb41, 0x1414);
    _setUpActor(USER2);
        Target.step();
        _delay(0x51251, 0xc117);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6d828, 0x1389);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3, 0x20);
    _setUpActor(USER1);
        Target.step();
        _delay(0x8af1a, 0xb);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4a0f1, 0x440);
    _setUpActor(USER4);
        Target.step();
        _delay(0x214c8, 0xea4d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x9, 0x138d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6d828, 0x2c);
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
