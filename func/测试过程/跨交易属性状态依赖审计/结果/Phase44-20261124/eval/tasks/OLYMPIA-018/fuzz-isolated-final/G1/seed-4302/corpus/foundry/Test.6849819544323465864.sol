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
        _delay(0x4eb3d, 0x755a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb38, 0x3ed9);
    _setUpActor(USER2);
        Target.step();
        _delay(0x63720, 0x1391);
    _setUpActor(USER1);
        Target.step();
        _delay(0x104c2, 0x1393);
    _setUpActor(USER3);
        Target.step();
        _delay(0x52be8, 0x440);
    _setUpActor(USER4);
        Target.step();
        _delay(0xc247, 0x2e81);
    _setUpActor(USER3);
        Target.step();
        _delay(0x5caa0, 0x139c);
    _setUpActor(USER2);
        Target.step();
        _delay(0x15, 0x2ea6);
    _setUpActor(USER1);
        Target.step();
        _delay(0x804a4, 0xd1ae);
    _setUpActor(USER2);
        Target.step();
        _delay(0x11d50, 0x85e0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x80772, 0x2f15);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4694f, 0x139f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x65410, 0x3032);
    _setUpActor(USER5);
        Target.step();
        _delay(0x2e1fe, 0x463);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1a, 0x2b60);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb33, 0x463);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6c82f, 0xd8f2);
    _setUpActor(USER4);
        Target.step();
        _delay(0x77bd0, 0x7fff);
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
