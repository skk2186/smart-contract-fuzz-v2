// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x30000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x50000);
    address constant USER4 = address(0x10000);
    address constant USER5 = address(0x20000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x6a9f7, 0x3);
    _setUpActor(USER1);
        Target.step();
        _delay(0x3e1ce, 0x1393);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7fff, 0x7fe1);
    _setUpActor(USER2);
        Target.step();
        _delay(0xffff, 0x12);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6c82f, 0x1379);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4c0ad, 0x1377);
    _setUpActor(USER4);
        Target.step();
        _delay(0x9, 0x4ddd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4a9a4, 0x95ce);
    _setUpActor(USER5);
        Target.step();
        _delay(0x3340a, 0x7f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x17, 0x16);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb43, 0x3c09);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4, 0x7630);
    _setUpActor(USER2);
        Target.step();
        _delay(0x24b01, 0x28);
    _setUpActor(USER1);
        Target.step();
        _delay(0x41a2, 0x440);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1051, 0x463);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb1d, 0x1385);
    _setUpActor(USER5);
        Target.step();
        _delay(0x3207c, 0x9cf);
    _setUpActor(USER5);
        Target.step();
        _delay(0x712e3, 0xf);
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
