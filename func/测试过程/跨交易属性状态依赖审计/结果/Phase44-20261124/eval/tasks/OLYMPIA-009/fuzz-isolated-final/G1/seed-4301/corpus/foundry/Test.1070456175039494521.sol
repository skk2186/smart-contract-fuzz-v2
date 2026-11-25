// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x50000);
    address constant USER3 = address(0x40000);
    address constant USER4 = address(0x30000);
    address constant USER5 = address(0x20000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x2b, 0x3c07);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb30, 0xeb58);
    _setUpActor(USER3);
        Target.step();
        _delay(0x11d50, 0x4);
    _setUpActor(USER4);
        Target.step();
        _delay(0x214ca, 0xc3b0);
    _setUpActor(USER4);
        Target.step();
        _delay(0xf, 0xd1ae);
    _setUpActor(USER5);
        Target.step();
        _delay(0x8345, 0xe8a0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb1d, 0xa19c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x37272, 0x1379);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb45, 0x755a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7cf4e, 0x2d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x62123, 0x19);
    _setUpActor(USER5);
        Target.step();
        _delay(0x13, 0x9de);
    _setUpActor(USER4);
        Target.step();
        _delay(0xd, 0x18);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6123, 0xea4f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x28, 0x7840);
    _setUpActor(USER5);
        Target.step();
        _delay(0x3340a, 0x552);
    _setUpActor(USER2);
        Target.step();
        _delay(0x329b9, 0xeb6b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x712e3, 0xea4e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7f, 0x107f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6ab84, 0x9d0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x43371, 0x20ff);
    _setUpActor(USER1);
        Target.step();
        _delay(0x3d, 0x94d4);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb38, 0x231);
    _setUpActor(USER3);
        Target.step();
        _delay(0x804a4, 0x1a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2cfe7, 0xea96);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1b73c, 0xb31c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x74d9f, 0x1360);
    _setUpActor(USER5);
        Target.step();
        _delay(0x11, 0x2f7b);
    _setUpActor(USER2);
        Target.step();
        _delay(0xd, 0x3c08);
    _setUpActor(USER5);
        Target.step();
        _delay(0x712e4, 0xd065);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7, 0x52c5);
    _setUpActor(USER5);
        Target.step();
        _delay(0xa, 0xcfae);
    _setUpActor(USER3);
        Target.step();
        _delay(0x10978, 0x2f15);
    _setUpActor(USER3);
        Target.step();
        _delay(0x11d50, 0x7321);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1b2da, 0xea4d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb1d, 0xcf13);
    _setUpActor(USER3);
        Target.step();
        _delay(0x17, 0x9d0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x75d98, 0x5d4d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7cf4e, 0x1);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb33, 0xdefe);
    _setUpActor(USER5);
        Target.step();
        _delay(0x3340a, 0x16);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4a0f1, 0x1378);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb07, 0xa4f5);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7f34, 0x3c08);
    _setUpActor(USER1);
        Target.step();
        _delay(0x9, 0x619b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3e1ce, 0x1363);
    _setUpActor(USER3);
        Target.step();
        _delay(0x76ea6, 0xada9);
    _setUpActor(USER5);
        Target.step();
        _delay(0xa, 0x753b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x22ac4, 0xea4d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x46b47, 0x138d);
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
