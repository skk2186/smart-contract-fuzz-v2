// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x10000);
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
        _delay(0x3340a, 0x5b6b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7d1b7, 0x1387);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb09, 0xea4e);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2d, 0x1377);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb3a, 0x753b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x43, 0x7630);
    _setUpActor(USER4);
        Target.step();
        _delay(0x5, 0x55ff);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6c82f, 0xd0cb);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1051, 0x139e);
    _setUpActor(USER5);
        Target.step();
        _delay(0x8f9df, 0x814e);
    _setUpActor(USER1);
        Target.step();
        _delay(0x3f, 0x13);
    _setUpActor(USER5);
        Target.step();
        _delay(0x29, 0x1414);
    _setUpActor(USER3);
        Target.step();
        _setUpActor(USER1);
        Target.step();
        _delay(0x2d, 0x4f13);
    _setUpActor(USER3);
        Target.step();
        _delay(0x23809, 0x7a00);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb41, 0x116e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x63160, 0x94d4);
    _setUpActor(USER4);
        Target.step();
        _delay(0x712e3, 0x86da);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3e1ce, 0xb0cd);
    _setUpActor(USER4);
        Target.bug();
        _delay(0x1cae0, 0x4ddd);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb3f, 0xcfae);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb31, 0x95ce);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1f113, 0x11);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1cae0, 0x2c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x64ad5, 0x1376);
    _setUpActor(USER5);
        Target.step();
        _delay(0x66815, 0x1377);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb39, 0x1395);
    _setUpActor(USER1);
        Target.step();
        _delay(0xc4f1, 0x8fad);
    _setUpActor(USER3);
        Target.step();
        _delay(0x27, 0xd8f2);
    _setUpActor(USER4);
        Target.step();
        _delay(0x42, 0xb337);
    _setUpActor(USER3);
        Target.step();
        _delay(0x65373, 0x41);
    _setUpActor(USER3);
        Target.step();
        _delay(0x18, 0xd13a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x41, 0x87a0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x2621e, 0x89b0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6c82f, 0x41);
    _setUpActor(USER1);
        Target.step();
        _delay(0x40, 0xcfae);
    _setUpActor(USER3);
        Target.step();
        _delay(0x46b47, 0x9cf);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb1e, 0x95ce);
    _setUpActor(USER2);
        Target.step();
        _delay(0x7, 0x7d93);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5f467, 0x440);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb30, 0x30cd);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7736a, 0x9d0);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb08, 0x1399);
    _setUpActor(USER3);
        Target.step();
        _delay(0x2975f, 0x13be);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb2f, 0xb64b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x7f7c2, 0xa40d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x63160, 0xd0cb);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eac7, 0x13);
    _setUpActor(USER4);
        Target.step();
        _delay(0x42, 0x41);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb34, 0x16);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb20, 0x3ed9);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb1d, 0x231);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb41, 0x4ddd);
    _setUpActor(USER2);
        Target.step();
        _delay(0xf, 0x1372);
    _setUpActor(USER5);
        Target.step();
        _delay(0x1a, 0x1376);
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
