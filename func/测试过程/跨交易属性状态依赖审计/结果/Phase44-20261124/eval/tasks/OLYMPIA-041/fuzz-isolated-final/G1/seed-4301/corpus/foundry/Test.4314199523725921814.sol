// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x50000);
    address constant USER4 = address(0x40000);
    address constant USER5 = address(0x10000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x142f0, 0x4a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x142f0, 0x63);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2c, 0xb31c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x10, 0x5d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb1c, 0x1382);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eae3, 0x1366);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5caa0, 0xb2fb);
    _setUpActor(USER3);
        Target.step();
        _delay(0xc4f1, 0xc22f);
    _setUpActor(USER2);
        Target.step();
        _delay(0x712e3, 0x137f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1d, 0x57);
    _setUpActor(USER1);
        Target.step();
        _delay(0x56, 0x1388);
    _setUpActor(USER1);
        Target.step();
        _delay(0xa622, 0xa);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eaf7, 0x5b6b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3a, 0x4562);
    _setUpActor(USER5);
        Target.step();
        _delay(0x94ab, 0x1360);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eae6, 0x137e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x64, 0x60f8);
    _setUpActor(USER5);
        Target.step();
        _delay(0x94ab, 0x1360);
    _setUpActor(USER4);
        Target.step();
        _delay(0x3e1ce, 0x1740);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb2c, 0x137d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x74d9f, 0x33);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb0e, 0xa4f5);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7, 0x1367);
    _setUpActor(USER4);
        Target.step();
        _delay(0x77bce, 0x1475);
    _setUpActor(USER4);
        Target.step();
        _delay(0x62e05, 0x1366);
    _setUpActor(USER3);
        Target.step();
        _delay(0x75578, 0x1366);
    _setUpActor(USER5);
        Target.step();
        _delay(0x63, 0x133f);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4197, 0x134d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2a, 0x9c1);
    _setUpActor(USER1);
        Target.step();
        _delay(0x40, 0x1a41);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb3a, 0x1414);
    _setUpActor(USER5);
        Target.step();
        _delay(0x1b73c, 0x1361);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eaff, 0xa4f5);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb3e, 0x137b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb03, 0x1372);
    _setUpActor(USER5);
        Target.step();
        _delay(0x55, 0xd619);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb41, 0xdefe);
    _setUpActor(USER3);
        Target.step();
        _delay(0x65410, 0x1370);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7eea7, 0xd5ba);
    _setUpActor(USER4);
        Target.step();
        _delay(0x5caa0, 0x1375);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eac7, 0x20ff);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6ae4e, 0x19);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4e655, 0xd619);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eae7, 0x65);
    _setUpActor(USER1);
        Target.step();
        _delay(0x46b47, 0x1343);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb0a, 0xd1ae);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8a317, 0xdae0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2f, 0xea4d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8035b, 0x1345);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb07, 0x116e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7eea7, 0x64);
    _setUpActor(USER5);
        Target.step();
        _delay(0x8345, 0xa);
    _setUpActor(USER3);
        Target.step();
        _delay(0x62, 0x1345);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8, 0x755a);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb28, 0x55a0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1c5dc, 0x138f);
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
