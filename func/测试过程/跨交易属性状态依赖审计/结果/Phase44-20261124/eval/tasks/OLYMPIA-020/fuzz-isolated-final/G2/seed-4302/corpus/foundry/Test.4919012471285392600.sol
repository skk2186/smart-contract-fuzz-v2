// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x50000);
    address constant USER4 = address(0x30000);
    address constant USER5 = address(0x10000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x9, 0x138f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x189e3, 0x1399);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb38, 0x5aeb);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7b6a, 0x1c9b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8aca6, 0x14);
    _setUpActor(USER3);
        Target.step();
        _delay(0x94ab, 0x8);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb3c, 0x320);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb35, 0xeb6b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x5, 0x2aa9);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb3d, 0x2e32);
    _setUpActor(USER2);
        Target.step();
        _delay(0x400be, 0x9de);
    _setUpActor(USER5);
        Target.step();
        _delay(0x142ee, 0x7840);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3, 0x89b0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x63720, 0x8ffb);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1c5dc, 0x16);
    _setUpActor(USER1);
        Target.step();
        _delay(0x475d0, 0xe8a0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb31, 0x597d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x668ee, 0x138f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x51251, 0x3);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7b6a, 0x3c07);
    _setUpActor(USER5);
        Target.step();
        _delay(0xb, 0xb2c2);
    _setUpActor(USER5);
        Target.step();
        _delay(0x16348, 0x87a0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x8af1a, 0xd619);
    _setUpActor(USER4);
        Target.step();
        _delay(0x142f0, 0x17);
    _setUpActor(USER5);
        Target.step();
        _delay(0x66815, 0x3);
    _setUpActor(USER1);
        Target.step();
        _delay(0x19, 0xff);
    _setUpActor(USER5);
        Target.step();
        _delay(0x80772, 0x139c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6d828, 0x139f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4, 0x619b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x12, 0x1390);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5aa87, 0xeb58);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4a55, 0x138d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1b2da, 0xea4d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x48a23, 0x1397);
    _setUpActor(USER5);
        Target.step();
        _delay(0x875e1, 0xea4d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x2fa33, 0x139c);
    _setUpActor(USER5);
        Target.step();
        _delay(0x12, 0x1391);
    _setUpActor(USER1);
        Target.step();
        _delay(0xf, 0x139f);
    _setUpActor(USER4);
        Target.step();
        _delay(0xd, 0x138a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6c82f, 0x7840);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5caa0, 0x4);
    _setUpActor(USER4);
        Target.step();
        _delay(0x80772, 0x138f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x76ea6, 0x1393);
    _setUpActor(USER1);
        Target.step();
        _delay(0x10, 0x1);
    _setUpActor(USER4);
        Target.step();
        _delay(0x61e55, 0x1740);
    _setUpActor(USER4);
        Target.step();
        _delay(0x329b9, 0x4);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb38, 0xa85f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x65373, 0xcfae);
    _setUpActor(USER5);
        Target.step();
        _delay(0x64ad5, 0x22bc);
    _setUpActor(USER4);
        Target.step();
        _delay(0x48a23, 0x138b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x212f1, 0x7840);
    _setUpActor(USER4);
        Target.step();
        _delay(0x48a23, 0x9d0);
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
