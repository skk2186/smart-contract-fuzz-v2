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
        _delay(0x2, 0x20ff);
    _setUpActor(USER1);
        Target.step();
        _delay(0x61e55, 0x7630);
    _setUpActor(USER1);
        Target.step();
        _delay(0x81f7, 0x5cdc);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4daf5, 0x5d4d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6d464, 0x7fe1);
    _setUpActor(USER3);
        Target.step();
        _delay(0xac13, 0x3e0c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb38, 0x3a9d);
    _setUpActor(USER1);
        Target.step();
        _delay(0xc4f1, 0xebcc);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb30, 0x1391);
    _setUpActor(USER5);
        Target.step();
        _delay(0x61e55, 0x95ce);
    _setUpActor(USER1);
        Target.step();
        _delay(0x77bce, 0x2ea6);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6a2ce, 0xeaeb);
    _setUpActor(USER2);
        Target.step();
        _delay(0x37272, 0x7d93);
    _setUpActor(USER3);
        Target.step();
        _delay(0xa, 0xb7e3);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb40, 0xd13a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x11, 0x139f);
    _setUpActor(USER2);
        Target.step();
        _delay(0x65373, 0x1394);
    _setUpActor(USER5);
        Target.step();
        _delay(0x712e3, 0xa4f5);
    _setUpActor(USER5);
        Target.step();
        _delay(0x8345, 0xeb58);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb44, 0x231);
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
