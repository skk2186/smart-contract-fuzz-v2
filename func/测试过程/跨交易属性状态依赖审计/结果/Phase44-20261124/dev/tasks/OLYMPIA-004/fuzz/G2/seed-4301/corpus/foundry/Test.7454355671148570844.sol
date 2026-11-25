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
        _delay(0x668ee, 0x9cf);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb33, 0x2a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5fe41, 0x4e5c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x62e05, 0x2e32);
    _setUpActor(USER1);
        Target.step();
        _setUpActor(USER4);
        Target.step();
        _delay(0x3e1ce, 0xd898);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6b504, 0x94d4);
    _setUpActor(USER4);
        Target.step();
        _delay(0x52be8, 0x7a00);
    _setUpActor(USER1);
        Target.step();
        _delay(0x668ee, 0x1475);
    _setUpActor(USER5);
        Target.step();
        _delay(0xc, 0x14);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4a55, 0x95ce);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6db58, 0xeb58);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4a9a4, 0x10);
    _setUpActor(USER4);
        Target.step();
        _delay(0x10, 0xb7e3);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eac7, 0x3);
    _setUpActor(USER4);
        Target.step();
        _delay(0x37272, 0x3032);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb33, 0x2a);
    _setUpActor(USER5);
        Target.step();
        _delay(0x46b47, 0x138b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x770f4, 0xd);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb2c, 0x7d93);
    _setUpActor(USER4);
        Target.step();
        _delay(0x52be8, 0x1386);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7fff, 0x7f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb39, 0x85e0);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1c18d, 0xebcc);
    _setUpActor(USER5);
        Target.step();
        _delay(0x2d, 0x1399);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2e, 0x87a0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7fff, 0x1b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x16, 0x89b0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb2d, 0x320);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb30, 0x107f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6d828, 0x9de);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eac7, 0x5b6b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x13, 0x95ce);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb32, 0xeb58);
    _setUpActor(USER5);
        Target.step();
        _delay(0x580b0, 0x139b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x66815, 0x647b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x48a23, 0xc);
    _setUpActor(USER3);
        Target.step();
        _delay(0x76ea6, 0x116e);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8af1a, 0x1387);
    _setUpActor(USER4);
        Target.step();
        _delay(0x28, 0x19);
    _setUpActor(USER5);
        Target.step();
        _delay(0x76ea6, 0x2588);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb3d, 0x3fea);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5caa0, 0x138f);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1b73c, 0xea4e);
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
