// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x50000);
    address constant USER5 = address(0x20000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x2152e, 0x1358);
    _setUpActor(USER1);
        Target.step();
        _delay(0x48, 0x1393);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4b, 0x56);
    _setUpActor(USER2);
        Target.step();
        _delay(0x57, 0x2a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb30, 0x138d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4, 0x8);
    _setUpActor(USER1);
        Target.step();
        _delay(0x3, 0x185a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb07, 0x139d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x49, 0x25);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eaee, 0xea4d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x5b, 0x9);
    _setUpActor(USER3);
        Target.step();
        _setUpActor(USER1);
        Target.step();
        _delay(0x50, 0x7f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb0c, 0x85e0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x85b27, 0xd0cb);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6a9f7, 0xa663);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1651d, 0x135b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x1e, 0xe4d);
    _setUpActor(USER5);
        Target.step();
        _delay(0xa, 0xea4e);
    _setUpActor(USER1);
        Target.step();
        _delay(0xd, 0x55);
    _setUpActor(USER1);
        Target.step();
        _delay(0x37272, 0x718a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1c5dc, 0x1347);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4c, 0x53);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb09, 0x1381);
    _setUpActor(USER5);
        Target.step();
        _delay(0x433c2, 0x1350);
    _setUpActor(USER4);
        Target.step();
        _delay(0x61, 0x1352);
    _setUpActor(USER4);
        Target.step();
        _delay(0x103ef, 0xd1ae);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb13, 0x3f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x15, 0xb31c);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb14, 0x46);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eaec, 0x9368);
    _setUpActor(USER2);
        Target.step();
        _delay(0x13, 0x3a9d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eaec, 0x30);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb1b, 0x1386);
    _setUpActor(USER4);
        Target.step();
        _delay(0x53, 0x1475);
    _setUpActor(USER2);
        Target.step();
        _delay(0x804a4, 0x1372);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb44, 0xd13a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eae1, 0x1);
    _setUpActor(USER5);
        Target.step();
        _delay(0x51251, 0x5caa);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5d, 0x25);
    _setUpActor(USER5);
        Target.step();
        _delay(0x66280, 0x1352);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5f, 0x136b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x65679, 0x320);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eae8, 0x137e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb17, 0x89b0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x2a, 0x53);
    _setUpActor(USER4);
        Target.step();
        _delay(0x48a47, 0x3f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb45, 0x1475);
    _setUpActor(USER1);
        Target.step();
        _delay(0x3256a, 0x1347);
    _setUpActor(USER3);
        Target.step();
        _delay(0x62e05, 0x3d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x668ee, 0x9cf);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eafc, 0x2e81);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb44, 0xb31c);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3e, 0x51);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb14, 0x3f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x61, 0x1362);
    _setUpActor(USER2);
        Target.step();
        _delay(0x53, 0x135f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5a, 0x1360);
    _setUpActor(USER4);
        Target.step();
        _delay(0x39, 0x7660);
    _setUpActor(USER2);
        Target.step();
        _delay(0xe, 0x7f);
    _setUpActor(USER4);
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
