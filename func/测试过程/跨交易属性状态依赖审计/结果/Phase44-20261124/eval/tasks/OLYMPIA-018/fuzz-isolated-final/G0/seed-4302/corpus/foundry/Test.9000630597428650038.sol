// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x50000);
    address constant USER2 = address(0x10000);
    address constant USER3 = address(0x20000);
    address constant USER4 = address(0x30000);
    address constant USER5 = address(0x40000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x142ef, 0x9de);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5644f, 0x3a9d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2d, 0x139e);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3f, 0x1391);
    _setUpActor(USER3);
        Target.step();
        _delay(0xc4f1, 0x139f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb32, 0x27e0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x212f1, 0x3c08);
    _setUpActor(USER5);
        Target.step();
        _delay(0x2fa33, 0x1398);
    _setUpActor(USER5);
        Target.step();
        _delay(0x90319, 0x2f15);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7cf4e, 0xb31c);
    _setUpActor(USER1);
        Target.step();
        _delay(0x784d9, 0x1394);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6b504, 0x26ee);
    _setUpActor(USER5);
        Target.step();
        _delay(0x8f9df, 0x47fd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb38, 0x3c09);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8a317, 0x87a0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb3f, 0xd);
    _setUpActor(USER3);
        Target.step();
        _delay(0x74d9f, 0x19);
    _setUpActor(USER2);
        Target.step();
        _delay(0x329b9, 0x1320);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1, 0xe8a0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x329b9, 0x7a00);
    _setUpActor(USER5);
        Target.step();
        _delay(0x142f0, 0x116e);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb2c, 0xf);
    _setUpActor(USER1);
        Target.step();
        _setUpActor(USER4);
        Target.step();
        _delay(0x1c18d, 0x3ed9);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7f467, 0xadb5);
    _setUpActor(USER4);
        Target.step();
        _delay(0x62e05, 0x5);
    _setUpActor(USER3);
        Target.step();
        _delay(0x51251, 0x3d8a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x62123, 0x1387);
    _setUpActor(USER5);
        Target.step();
        _delay(0x8345, 0x2e81);
    _setUpActor(USER5);
        Target.step();
        _delay(0x1f113, 0xe8a0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb2c, 0xe);
    _setUpActor(USER2);
        Target.step();
        _delay(0x8af1a, 0x4);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2fa33, 0x231);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3f, 0x7660);
    _setUpActor(USER2);
        Target.step();
        _delay(0x90fc3, 0x2c55);
    _setUpActor(USER5);
        Target.step();
        _delay(0x19, 0xa4f5);
    _setUpActor(USER4);
        Target.step();
        _delay(0x804a4, 0x89b0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x329b9, 0x7840);
    _setUpActor(USER2);
        Target.step();
        _delay(0x142f0, 0x13);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1c5dc, 0xd619);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eac7, 0xd1ae);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6b504, 0xc107);
    _setUpActor(USER1);
        Target.step();
        _delay(0x11, 0x94d4);
    _setUpActor(USER5);
        Target.step();
        _delay(0x62123, 0xd38b);
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
