// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x40000);
    address constant USER4 = address(0x20000);
    address constant USER5 = address(0x50000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x7, 0x4e);
    _setUpActor(USER1);
        Target.step();
        _delay(0x712e4, 0x824d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb3c, 0xd13a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x8633d, 0xe8a0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eae6, 0x19);
    _setUpActor(USER1);
        Target.step();
        _delay(0x214ca, 0x1372);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb3c, 0x56);
    _setUpActor(USER2);
        Target.step();
        _delay(0xb056, 0x6b0c);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7cf4e, 0x60);
    _setUpActor(USER2);
        Target.step();
        _delay(0x900e6, 0xb31c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x11, 0x4b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x5dd3a, 0x135d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x77bce, 0x440);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb1a, 0x5e71);
    _setUpActor(USER4);
        Target.step();
        _delay(0xc, 0x1364);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eaf1, 0x138c);
    _setUpActor(USER5);
        Target.step();
        _delay(0x329b9, 0x1399);
    _setUpActor(USER1);
        Target.step();
        _delay(0x28, 0xb31c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x74d9f, 0x136f);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4e45c, 0x1341);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1b2da, 0x5b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eae8, 0x134a);
    _setUpActor(USER5);
        Target.step();
        _delay(0x45, 0x4e);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7d1b7, 0x30);
    _setUpActor(USER5);
        Target.step();
        _delay(0x33, 0xd8f2);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1051, 0x4);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3e1ce, 0x6b80);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb23, 0x1381);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb09, 0x53);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1f113, 0x26ee);
    _setUpActor(USER5);
        Target.step();
        _delay(0x2cbdc, 0x20);
    _setUpActor(USER1);
        Target.step();
        _delay(0x61, 0xe4ce);
    _setUpActor(USER5);
        Target.step();
        _delay(0x51, 0x139a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2621e, 0x29);
    _setUpActor(USER1);
        Target.step();
        _delay(0xc4f1, 0x2f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x22, 0x134a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6b684, 0x1364);
    _setUpActor(USER3);
        Target.step();
        _delay(0x475d0, 0x1396);
    _setUpActor(USER5);
        Target.step();
        _delay(0xe, 0xff);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb2a, 0x1414);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3f970, 0x1356);
    _setUpActor(USER4);
        Target.step();
        _delay(0x27, 0x85e0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eaf8, 0x5daa);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7e036, 0x58);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb12, 0x7d93);
    _setUpActor(USER3);
        Target.step();
        _delay(0x17, 0x23);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1e, 0x133f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x5f467, 0xcf13);
    _setUpActor(USER2);
        Target.step();
        _delay(0x26, 0x5f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x28928, 0x20ff);
    _setUpActor(USER5);
        Target.step();
        _setUpActor(USER2);
        Target.step();
        _delay(0x6a2ce, 0x1344);
    _setUpActor(USER1);
        Target.step();
        _delay(0x3f, 0x5f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x61e55, 0x48);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb06, 0xea63);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2b, 0x65);
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
