// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x20000);
    address constant USER3 = address(0x30000);
    address constant USER4 = address(0x40000);
    address constant USER5 = address(0x50000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x7d1b7, 0x1385);
    _setUpActor(USER1);
        Target.step();
        _delay(0x11, 0x3c08);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6b721, 0xd619);
    _setUpActor(USER3);
        Target.step();
        _delay(0x214c8, 0x94d4);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7, 0x138e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x80201, 0x5);
    _setUpActor(USER4);
        Target.step();
        _delay(0x329b9, 0x27);
    _setUpActor(USER1);
        Target.step();
        _delay(0x214c8, 0x231);
    _setUpActor(USER2);
        Target.step();
        _delay(0x65373, 0xaa16);
    _setUpActor(USER5);
        Target.step();
        _delay(0x433c2, 0x4f13);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4694f, 0xeb58);
    _setUpActor(USER5);
        Target.step();
        _delay(0xf, 0x7c0);
    _setUpActor(USER4);
        Target.step();
        _delay(0x10, 0x1378);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb32, 0xa4f5);
    _setUpActor(USER3);
        Target.step();
        _delay(0x12, 0x20ff);
    _setUpActor(USER5);
        Target.step();
        _delay(0xf, 0xe8a0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x582b0, 0x139e);
    _setUpActor(USER3);
        Target.step();
        _delay(0x712e4, 0x139a);
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
