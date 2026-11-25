// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x50000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x20000);
    address constant USER4 = address(0x10000);
    address constant USER5 = address(0x40000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eb35, 0x1381);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb24, 0x46);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6, 0x4c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x59, 0x89b0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1c, 0x136f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x668ee, 0x518b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb12, 0x1350);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb27, 0x12);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6a9f7, 0x136b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb46, 0x139a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7b7a0, 0x4a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7cf4e, 0x35);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb2f, 0x37);
    _setUpActor(USER1);
        Target.step();
        _delay(0x62, 0x1374);
    _setUpActor(USER4);
        Target.step();
        _delay(0x65679, 0xc543);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaf8, 0x51);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eafb, 0x4ddd);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5b, 0x5b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb43, 0x1394);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7f7c2, 0x2ea6);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb1a, 0x2c55);
    _setUpActor(USER2);
        Target.step();
        _delay(0x62123, 0x1393);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb1e, 0x45d7);
    _setUpActor(USER1);
        Target.step();
        _delay(0x41, 0x3);
    _setUpActor(USER5);
        Target.step();
        _delay(0x3b, 0x7d93);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8, 0xd13a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaec, 0x29);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5f467, 0x9cf);
    _setUpActor(USER4);
        Target.step();
        _delay(0x43, 0xcf13);
    _setUpActor(USER2);
        Target.step();
        _delay(0x189e3, 0x1398);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eae7, 0x35);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eaf1, 0x20);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4, 0x5c65);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb21, 0x89b0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb27, 0xd6d9);
    _setUpActor(USER5);
        Target.step();
        _delay(0x58, 0x5c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x13, 0x58);
    _setUpActor(USER3);
        Target.step();
        _delay(0x2f, 0x2c55);
    _setUpActor(USER1);
        Target.step();
        _delay(0xa3, 0x57);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5a, 0x9947);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eae5, 0xaeee);
    _setUpActor(USER4);
        Target.step();
        _delay(0x584e4, 0x4ddd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x38, 0x53);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eac7, 0x47fd);
    _setUpActor(USER5);
        Target.step();
        _delay(0x189e3, 0x138d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eafb, 0x753b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x46b47, 0x35);
    _setUpActor(USER5);
        Target.step();
        _delay(0x50, 0xb0cd);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6c82f, 0x5c65);
    _setUpActor(USER3);
        Target.step();
        _delay(0x77bce, 0x1b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4f, 0x41);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1127d, 0x2);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4f, 0x2f15);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb38, 0x21);
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
