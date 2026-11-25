// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x50000);
    address constant USER4 = address(0x10000);
    address constant USER5 = address(0x30000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x22, 0x135d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6d828, 0x3c08);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1, 0x32);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eaf7, 0x60);
    _setUpActor(USER3);
        Target.step();
        _delay(0x189e3, 0x5d4d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eaf3, 0xa4f5);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaef, 0xd8f2);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eaf0, 0x7d93);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb23, 0x5d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x19, 0x1352);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1d, 0x7);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eafe, 0x30);
    _setUpActor(USER1);
        Target.step();
        _delay(0xb056, 0x9cf);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb02, 0x2d8f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaea, 0x5892);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4a0f1, 0x36);
    _setUpActor(USER1);
        Target.step();
        _delay(0x214c8, 0xb31c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb0d, 0x9cf);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb0b, 0x3032);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb2c, 0x1350);
    _setUpActor(USER3);
        Target.step();
        _delay(0x15, 0x133e);
    _setUpActor(USER2);
        Target.step();
        _delay(0xfba5, 0x1391);
    _setUpActor(USER1);
        Target.step();
        _delay(0x875e1, 0x1d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x81f7, 0xd5ce);
    _setUpActor(USER4);
        Target.step();
        _delay(0x37231, 0x2b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb12, 0xb556);
    _setUpActor(USER4);
        Target.step();
        _delay(0x39, 0x133d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eae4, 0x1366);
    _setUpActor(USER3);
        Target.step();
        _delay(0xf, 0x136e);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1c, 0x3a);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb0f, 0x134c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x78ae4, 0x66a7);
    _setUpActor(USER2);
        Target.step();
        _delay(0x28, 0x3a9d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x34, 0x1357);
    _setUpActor(USER4);
        Target.step();
        _delay(0x38, 0x9c55);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb0b, 0x1347);
    _setUpActor(USER1);
        Target.step();
        _delay(0xc, 0x1358);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eafe, 0x58ab);
    _setUpActor(USER2);
        Target.step();
        _delay(0x94ab, 0x1389);
    _setUpActor(USER5);
        Target.step();
        _delay(0x214c9, 0x2ea6);
    _setUpActor(USER2);
        Target.step();
        _delay(0x24, 0x23);
    _setUpActor(USER2);
        Target.step();
        _delay(0x63160, 0x2f7b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7f7c2, 0x54);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eafb, 0x135c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x63160, 0x556);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb45, 0x1381);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb20, 0xd8f2);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb20, 0x1475);
    _setUpActor(USER4);
        Target.step();
        _delay(0x582b0, 0x133b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4f, 0x1367);
    _setUpActor(USER5);
        Target.step();
        _delay(0x2b, 0x94d4);
    _setUpActor(USER4);
        Target.step();
        _delay(0x80772, 0x20);
    _setUpActor(USER5);
        Target.step();
        _delay(0xc247, 0x1369);
    _setUpActor(USER3);
        Target.step();
        _delay(0x872c1, 0x4c);
    _setUpActor(USER1);
        Target.step();
        _delay(0x48a23, 0x10);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb08, 0x755a);
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
