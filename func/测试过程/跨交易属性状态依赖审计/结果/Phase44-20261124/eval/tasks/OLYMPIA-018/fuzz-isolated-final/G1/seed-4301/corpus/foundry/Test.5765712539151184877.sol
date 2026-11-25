// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x30000);
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
        _delay(0x14, 0x753b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb35, 0x5aeb);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2bbcc, 0x7275);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3f, 0xe59f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8f9df, 0x5b6b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8f9df, 0x1397);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7b6a, 0x3c07);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7f7c2, 0xc543);
    _setUpActor(USER3);
        Target.step();
        _delay(0x81f7, 0x9);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2c, 0x1393);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb31, 0x12);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb35, 0x7);
    _setUpActor(USER3);
        Target.step();
        _delay(0x51251, 0x47fd);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7fff, 0x95ce);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb33, 0x139b);
    _setUpActor(USER5);
        Target.step();
        _delay(0xffff, 0x1a);
    _setUpActor(USER5);
        Target.step();
        _delay(0x9, 0x7c0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x576ad, 0xd619);
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
