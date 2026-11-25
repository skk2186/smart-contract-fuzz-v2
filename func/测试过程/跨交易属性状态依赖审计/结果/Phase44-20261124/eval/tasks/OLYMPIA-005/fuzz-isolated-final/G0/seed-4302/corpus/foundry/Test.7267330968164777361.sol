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
        _delay(0x580b0, 0x20ff);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6, 0x824d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x8f9df, 0xa663);
    _setUpActor(USER1);
        Target.step();
        _delay(0x62123, 0xb31c);
    _setUpActor(USER3);
        Target.step();
        _delay(0xc247, 0x2ea6);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4694f, 0xe59f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x214c8, 0x5d4d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x66815, 0x8ffb);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1051, 0x139f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6d464, 0xd1ae);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6a9f7, 0x8ec3);
    _setUpActor(USER3);
        Target.step();
        _delay(0x17, 0x1320);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7, 0x30c9);
    _setUpActor(USER4);
        Target.step();
        _delay(0x66815, 0x138e);
    _setUpActor(USER1);
        Target.step();
        _delay(0xf, 0x463);
    _setUpActor(USER1);
        Target.step();
        _delay(0x15, 0x755a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7f467, 0x95ce);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb43, 0x1395);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb30, 0xc107);
    _setUpActor(USER3);
        Target.step();
        _delay(0x5408b, 0xccc2);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2f, 0xa);
    _setUpActor(USER2);
        Target.step();
        _delay(0x62041, 0x440c);
    _setUpActor(USER2);
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
