// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x50000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x20000);
    address constant USER5 = address(0x30000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4d3a5, 0x440);
    _setUpActor(USER1);
        Target.step();
        _delay(0x329b9, 0x2f15);
    _setUpActor(USER2);
        Target.step();
        _delay(0x142ef, 0x95ce);
    _setUpActor(USER3);
        Target.step();
        _delay(0x222f6, 0xc107);
    _setUpActor(USER5);
        Target.step();
        _delay(0xb056, 0x463);
    _setUpActor(USER1);
        Target.step();
        _delay(0x11, 0x9de);
    _setUpActor(USER1);
        Target.step();
        _delay(0xc, 0xa2eb);
    _setUpActor(USER2);
        Target.step();
        _delay(0xf, 0x552);
    _setUpActor(USER4);
        Target.step();
        _delay(0x5, 0xd619);
    _setUpActor(USER3);
        Target.step();
        _delay(0x5, 0xc);
    _setUpActor(USER5);
        Target.step();
        _delay(0x804a4, 0xdefe);
    _setUpActor(USER4);
        Target.step();
        _delay(0xc4f1, 0xeb6b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x63160, 0x1a41);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb33, 0x1388);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6b721, 0x26c0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb3e, 0x7660);
    _setUpActor(USER2);
        Target.step();
        _delay(0x11d50, 0x1387);
    _setUpActor(USER2);
        Target.step();
        _delay(0x214ca, 0x1388);
    _setUpActor(USER5);
        Target.step();
        _delay(0x61e55, 0x7);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6d828, 0x16);
    _setUpActor(USER1);
        Target.step();
        _delay(0x28928, 0x139f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb30, 0x1395);
    _setUpActor(USER1);
        Target.step();
        _delay(0x16, 0x9c1);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb45, 0x3c07);
    _setUpActor(USER3);
        Target.step();
        _delay(0xc4f1, 0xd065);
    _setUpActor(USER5);
        Target.step();
        _delay(0x15, 0x1b62);
    _setUpActor(USER3);
        Target.step();
        _delay(0x80772, 0x7630);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1b2da, 0xc107);
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
