// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x10000);
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
        _delay(0x5d89, 0x12);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5caa0, 0x1740);
    _setUpActor(USER2);
        Target.step();
        _delay(0x77bce, 0x116e);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7d1b7, 0xd38b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x10fd5, 0xd13a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb35, 0x7f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1a, 0x1393);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3340a, 0x6d6e);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1051, 0xc924);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6a9f7, 0x20ff);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb42, 0x7d93);
    _setUpActor(USER4);
        Target.step();
        _delay(0x712e4, 0x7);
    _setUpActor(USER3);
        Target.step();
        _delay(0x63160, 0xd065);
    _setUpActor(USER4);
        Target.step();
        _delay(0x85b27, 0x2e81);
    _setUpActor(USER2);
        Target.step();
        _delay(0x88df5, 0x1389);
    _setUpActor(USER1);
        Target.step();
        _delay(0xc4f1, 0x9cf);
    _setUpActor(USER1);
        Target.step();
        _delay(0x212f1, 0x139d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x19, 0x1392);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb34, 0x139f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x24b01, 0x5f16);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2fa33, 0x1320);
    _setUpActor(USER3);
        Target.step();
        _delay(0x74d9f, 0xb6fa);
    _setUpActor(USER5);
        Target.step();
        _delay(0xd, 0x138c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x668ee, 0x7f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x142ee, 0x1398);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb3f, 0x231);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb42, 0x2ea6);
    _setUpActor(USER3);
        Target.step();
        _delay(0x2, 0x139c);
    _setUpActor(USER5);
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
