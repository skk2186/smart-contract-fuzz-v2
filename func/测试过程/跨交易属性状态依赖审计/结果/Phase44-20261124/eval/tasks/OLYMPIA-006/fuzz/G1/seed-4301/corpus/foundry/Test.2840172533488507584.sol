// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x30000);
    address constant USER2 = address(0x50000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x40000);
    address constant USER5 = address(0x20000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eb34, 0x7e4f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6b504, 0x138e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x52be8, 0x1475);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6c82f, 0x9d0);
    _setUpActor(USER4);
        Target.step();
        _delay(0x580b0, 0x7fff);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5f467, 0x1740);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb35, 0x8);
    _setUpActor(USER1);
        Target.step();
        _delay(0x3, 0xc);
    _setUpActor(USER5);
        Target.step();
        _delay(0xc, 0x218a);
    _setUpActor(USER5);
        Target.step();
        _delay(0xe, 0x7fff);
    _setUpActor(USER4);
        Target.step();
        _delay(0x56756, 0xe8a0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6d464, 0x138d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3f, 0x13);
    _setUpActor(USER1);
        Target.step();
        _delay(0x41a2, 0xea4d);
    _setUpActor(USER2);
        Target.step();
        _delay(0xff, 0x116e);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2d, 0x139d);
    _setUpActor(USER3);
        Target.step();
        _setUpActor(USER1);
        Target.step();
        _delay(0x214c9, 0x2);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6123, 0x1377);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1691f, 0x3a19);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4daf5, 0x1a41);
    _setUpActor(USER3);
        Target.step();
        _delay(0x15, 0x138a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7, 0x10);
    _setUpActor(USER3);
        Target.step();
        _delay(0x2, 0x30cd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x10, 0x20ff);
    _setUpActor(USER3);
        Target.step();
        _delay(0x24b01, 0x2f15);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2c, 0xc97f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4694f, 0x1740);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb2f, 0x13bd);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb1d, 0x1391);
    _setUpActor(USER5);
        Target.step();
        _delay(0x10978, 0x87a0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4969e, 0xd13a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x24b01, 0xe3ab);
    _setUpActor(USER1);
        Target.step();
        _delay(0xb, 0x30cd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1b2da, 0x1a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8a317, 0x619b);
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
