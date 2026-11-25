// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x50000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x30000);
    address constant USER5 = address(0x20000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x13, 0x138d);
    _setUpActor(USER1);
        Target.step();
        _delay(0xbd, 0x5a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eaee, 0x12d5);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4e, 0x5a1f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb3a, 0xa5);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eac6, 0x12c3);
    _setUpActor(USER4);
        Target.step();
        _delay(0x877b, 0x136a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4ea81, 0xb0cd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eaf6, 0x12c5);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb30, 0xdb);
    _setUpActor(USER5);
        Target.step();
        _delay(0xdb, 0x12d7);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4ea6f, 0xb1);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eab0, 0x8b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3a, 0x1361);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4ea7e, 0xb2);
    _setUpActor(USER2);
        Target.step();
        _delay(0x8b, 0x12d6);
    _setUpActor(USER4);
        Target.step();
        _delay(0x3e, 0xb38c);
    _setUpActor(USER3);
        Target.step();
        _delay(0xbc, 0x30);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4ea66, 0x1377);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4ea91, 0x709d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eada, 0x98);
    _setUpActor(USER5);
        Target.step();
        _delay(0x666e7, 0x1362);
    _setUpActor(USER4);
        Target.step();
        _delay(0x61e55, 0x1390);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4ea95, 0x1358);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4ead1, 0x12d3);
    _setUpActor(USER3);
        Target.step();
        _delay(0xb056, 0x1303);
    _setUpActor(USER3);
        Target.step();
        _delay(0x36, 0x12d7);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eaf4, 0x1396);
    _setUpActor(USER5);
        Target.step();
        _delay(0x63, 0x88);
    _setUpActor(USER2);
        Target.step();
        _delay(0x886fd, 0x6b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x79, 0xe278);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3f3cd, 0x139c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4e, 0x27);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eab2, 0x47fd);
    _setUpActor(USER3);
        Target.step();
        _delay(0xa5, 0x1364);
    _setUpActor(USER2);
        Target.step();
        _delay(0x214c9, 0x89);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6b, 0x9a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eaaf, 0x97);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eae9, 0x61);
    _setUpActor(USER5);
        Target.step();
        _delay(0x16a6d, 0x5b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6ae4e, 0x1c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6, 0x1321);
    _setUpActor(USER3);
        Target.step();
        _delay(0x76, 0x2f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4ea7c, 0x27);
    _setUpActor(USER3);
        Target.step();
        _delay(0xa0, 0xb0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb20, 0x1355);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6e, 0x12cf);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaf9, 0x1361);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4ea98, 0x73);
    _setUpActor(USER3);
        Target.step();
        _delay(0xbe, 0x9c1);
    _setUpActor(USER3);
        Target.step();
        _delay(0xd6, 0x552);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4ea9c, 0x1302);
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
