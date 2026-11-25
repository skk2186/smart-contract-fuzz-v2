// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x20000);
    address constant USER3 = address(0x50000);
    address constant USER4 = address(0x30000);
    address constant USER5 = address(0x40000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4a0f1, 0x1362);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7eea7, 0xbfde);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5b, 0x753b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x55, 0x9c1);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb13, 0x1389);
    _setUpActor(USER4);
        Target.step();
        _delay(0x62e05, 0x1385);
    _setUpActor(USER4);
        Target.step();
        _delay(0x85b27, 0x1c9b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb42, 0x4c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eae2, 0x1381);
    _setUpActor(USER3);
        Target.step();
        _delay(0x65373, 0x7840);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1a, 0x2ea6);
    _setUpActor(USER3);
        Target.step();
        _delay(0x387db, 0x31);
    _setUpActor(USER4);
        Target.step();
        _delay(0x3340a, 0x13be);
    _setUpActor(USER3);
        Target.step();
        _delay(0x25, 0x11);
    _setUpActor(USER4);
        Target.step();
        _delay(0x54, 0x9de);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7f467, 0xc6f0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x3e, 0x1475);
    _setUpActor(USER4);
        Target.step();
        _delay(0xc4f1, 0x8980);
    _setUpActor(USER5);
        Target.step();
        _delay(0x30, 0xd8f2);
    _setUpActor(USER4);
        Target.step();
        _delay(0x61db7, 0x2ea6);
    _setUpActor(USER3);
        Target.step();
        _delay(0x31, 0x1393);
    _setUpActor(USER4);
        Target.step();
        _delay(0x3256a, 0x4a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eae8, 0x4d);
    _setUpActor(USER5);
        Target.step();
        _delay(0xb86, 0x138a);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eaf2, 0x54);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb08, 0x1384);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1c, 0x1368);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaf9, 0x136c);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7ca27, 0x748f);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb01, 0x1b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x74d9f, 0x1382);
    _setUpActor(USER5);
        Target.step();
        _delay(0x1051, 0x4d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb04, 0xb);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb0f, 0x2ea6);
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
