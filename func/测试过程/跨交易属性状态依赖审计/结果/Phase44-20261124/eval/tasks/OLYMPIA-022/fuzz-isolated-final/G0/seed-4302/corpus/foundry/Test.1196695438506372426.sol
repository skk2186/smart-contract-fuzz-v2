// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x50000);
    address constant USER3 = address(0x30000);
    address constant USER4 = address(0x40000);
    address constant USER5 = address(0x10000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x2a, 0xd0cb);
    _setUpActor(USER1);
        Target.step();
        _delay(0x77bce, 0x28);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1b73c, 0x5550);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4a9a4, 0x20ff);
    _setUpActor(USER3);
        Target.step();
        _delay(0x42655, 0x5daa);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5caa0, 0x2a);
    _setUpActor(USER2);
        Target.step();
        _delay(0xc247, 0x1385);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1b, 0x138d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb1e, 0xd065);
    _setUpActor(USER2);
        Target.step();
        _delay(0x10, 0x2b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x8a317, 0x2c);
    _setUpActor(USER1);
        Target.step();
        _delay(0x3256a, 0xb556);
    _setUpActor(USER2);
        Target.step();
        _delay(0x66815, 0x29);
    _setUpActor(USER1);
        Target.step();
        _delay(0xe, 0x1389);
    _setUpActor(USER5);
        Target.step();
        _delay(0x1d911, 0x6b0c);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb39, 0xb2fb);
    _setUpActor(USER2);
        Target.step();
        _delay(0x214ca, 0x12);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3d, 0x1389);
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
