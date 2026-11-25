// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x20000);
    address constant USER3 = address(0x30000);
    address constant USER4 = address(0x50000);
    address constant USER5 = address(0x10000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x1b73c, 0x260b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x14, 0x1374);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2658c, 0x7a00);
    _setUpActor(USER3);
        Target.step();
        _delay(0x65373, 0x2e81);
    _setUpActor(USER3);
        Target.step();
        _delay(0x77bce, 0x7d93);
    _setUpActor(USER2);
        Target.step();
        _delay(0x64ad5, 0x94d4);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4a9a4, 0x597d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb38, 0x824d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6d464, 0x4);
    _setUpActor(USER5);
        Target.step();
        _delay(0x10978, 0xd13a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb34, 0x2ea6);
    _setUpActor(USER4);
        Target.step();
        _delay(0xffff, 0x139d);
    _setUpActor(USER3);
        Target.step();
        _delay(0xb056, 0xeb6b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1051, 0x7f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1b, 0x3c09);
    _setUpActor(USER3);
        Target.step();
        _delay(0x27, 0xd8f2);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4694f, 0x1);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7d1b7, 0x15);
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
