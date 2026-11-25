// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x50000);
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
        _delay(0x28928, 0x47fd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x19, 0x20ff);
    _setUpActor(USER2);
        Target.step();
        _delay(0x77bce, 0x20);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb1a, 0x58ab);
    _setUpActor(USER4);
        Target.step();
        _delay(0xb056, 0x1377);
    _setUpActor(USER2);
        Target.step();
        _delay(0x51251, 0x9cf);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6a2ce, 0x552);
    _setUpActor(USER5);
        Target.step();
        _delay(0x75d98, 0x755a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x27, 0x116e);
    _setUpActor(USER3);
        Target.step();
        _delay(0x19, 0x7840);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1cae0, 0x1395);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb3c, 0x13be);
    _setUpActor(USER5);
        Target.step();
        _delay(0x307c6, 0x185a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x7fff, 0x139e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x18, 0xd13a);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb1d, 0x13);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb1b, 0x10);
    _setUpActor(USER2);
        Target.step();
        _delay(0x11bfd, 0x231);
    _setUpActor(USER2);
        Target.step();
        _delay(0x48a23, 0x73a5);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb32, 0x8fc9);
    _setUpActor(USER5);
        Target.step();
        _delay(0xffff, 0x1a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x60749, 0x2d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb45, 0x1a41);
    _setUpActor(USER3);
        Target.step();
        _delay(0x5f1ec, 0x7660);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb41, 0x4e6d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x212f1, 0x2e32);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6, 0x11a1);
    _setUpActor(USER4);
        Target.step();
        _delay(0x11d50, 0x95ce);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb44, 0xeb6b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb45, 0x1388);
    _setUpActor(USER1);
        Target.step();
        _delay(0x73a32, 0x5c65);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb40, 0xd13a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6b721, 0x5ef7);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb30, 0x7f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x66815, 0x2ea6);
    _setUpActor(USER5);
        Target.step();
        _delay(0x65679, 0x2);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb40, 0x107f);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb35, 0x7);
    _setUpActor(USER1);
        Target.step();
        _delay(0x3, 0x20ff);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb1b, 0xb7e3);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1b2da, 0x30cd);
    _setUpActor(USER4);
        Target.step();
        _delay(0xe, 0x1378);
    _setUpActor(USER3);
        Target.step();
        _delay(0x712e3, 0x7630);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1cae0, 0x8);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6ae4e, 0xbd59);
    _setUpActor(USER5);
        Target.step();
        _delay(0xc4f1, 0x139f);
    _setUpActor(USER2);
        Target.step();
        _delay(0x75d98, 0x13bd);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb19, 0x87a0);
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
