// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x20000);
    address constant USER4 = address(0x40000);
    address constant USER5 = address(0x50000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eaeb, 0x31e4);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4a55, 0x2e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eaeb, 0xb556);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1b73c, 0x59);
    _setUpActor(USER2);
        Target.step();
        _delay(0x47ea, 0x1c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x5b, 0x1390);
    _setUpActor(USER2);
        Target.step();
        _delay(0x52be8, 0x25);
    _setUpActor(USER4);
        Target.step();
        _delay(0x36, 0x31);
    _setUpActor(USER1);
        Target.step();
        _delay(0x21, 0xd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eafd, 0x231);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb45, 0x5b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb11, 0x33);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5bd20, 0x1364);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb04, 0xa663);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb09, 0x137a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb15, 0x133b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x28928, 0x4af8);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb36, 0x134b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb25, 0x89b0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb13, 0xa77d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x3c, 0x9de);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7d1b7, 0x7840);
    _setUpActor(USER3);
        Target.step();
        _delay(0x61e55, 0x7159);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6a2ce, 0xe4d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb29, 0x44f8);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3f, 0x4e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb1a, 0xd065);
    _setUpActor(USER5);
        Target.step();
        _delay(0x62e05, 0x3c07);
    _setUpActor(USER4);
        Target.step();
        _delay(0x56, 0x6fca);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb0f, 0x901f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x214ca, 0x1356);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb17, 0x1381);
    _setUpActor(USER1);
        Target.step();
        _delay(0x29, 0x552);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eaee, 0x16);
    _setUpActor(USER3);
        Target.step();
        _delay(0x74d9f, 0x30);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb3a, 0x136f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x142ee, 0x133d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x46, 0x2f15);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2621e, 0x878e);
    _setUpActor(USER3);
        Target.step();
        _delay(0x64ad5, 0x1368);
    _setUpActor(USER2);
        Target.step();
        _delay(0x21, 0x1351);
    _setUpActor(USER1);
        Target.step();
        _delay(0x307c6, 0x138f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3a, 0x1389);
    _setUpActor(USER2);
        Target.step();
        _delay(0x36, 0x4e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x214c8, 0x24);
    _setUpActor(USER1);
        Target.step();
        _delay(0x329b9, 0x89b0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x57, 0xf);
    _setUpActor(USER5);
        Target.step();
        _delay(0x41, 0x85e0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5e, 0x37);
    _setUpActor(USER2);
        Target.step();
        _delay(0x20, 0x4ddd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eaf6, 0x43);
    _setUpActor(USER3);
        Target.step();
        _delay(0x51251, 0xe8da);
    _setUpActor(USER5);
        Target.step();
        _setUpActor(USER4);
        Target.step();
        _delay(0x60, 0x87a0);
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
