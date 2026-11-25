// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x30000);
    address constant USER2 = address(0x20000);
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
        _delay(0x62e05, 0x1399);
    _setUpActor(USER1);
        Target.step();
        _delay(0x307c6, 0x87a0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5408b, 0x1396);
    _setUpActor(USER4);
        Target.step();
        _delay(0xf, 0x7f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb32, 0x3b9a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x935e0, 0xea96);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2fa33, 0x9cf);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3e, 0x7);
    _setUpActor(USER4);
        Target.step();
        _delay(0x51251, 0x9de);
    _setUpActor(USER4);
        Target.step();
        _delay(0x76ea6, 0x6);
    _setUpActor(USER3);
        Target.step();
        _delay(0xe, 0x2f15);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6d828, 0xd619);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4, 0x7840);
    _setUpActor(USER3);
        Target.step();
        _delay(0x63720, 0xa4f5);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8b7a6, 0x12);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1b73c, 0x26ee);
    _setUpActor(USER5);
        Target.step();
        _delay(0x1051, 0x3c07);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1f113, 0x1388);
    _setUpActor(USER5);
        Target.step();
        _delay(0x142ee, 0x1378);
    _setUpActor(USER1);
        Target.step();
        _delay(0x580b0, 0x26ee);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8288, 0xa663);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb32, 0xea4f);
    _setUpActor(USER1);
        Target.step();
        _setUpActor(USER1);
        Target.step();
        _delay(0xb056, 0xdefe);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4a55, 0x2165);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7d1b7, 0x2f15);
    _setUpActor(USER1);
        Target.bug();
        _delay(0x15, 0x28);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb46, 0xab31);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb45, 0xd0cb);
    _setUpActor(USER5);
        Target.step();
        _delay(0x212f1, 0x3);
    _setUpActor(USER5);
        Target.step();
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
