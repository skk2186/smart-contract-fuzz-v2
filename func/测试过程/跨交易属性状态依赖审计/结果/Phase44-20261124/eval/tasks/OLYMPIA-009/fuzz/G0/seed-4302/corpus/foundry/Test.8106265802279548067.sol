// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x10000);
    address constant USER3 = address(0x50000);
    address constant USER4 = address(0x20000);
    address constant USER5 = address(0x30000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x6ae4e, 0x9de);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2e, 0x1363);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb3f, 0x1475);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1cae0, 0x29);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3d27, 0x5aeb);
    _setUpActor(USER2);
        Target.step();
        _delay(0x27, 0x13bd);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb42, 0xb31c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb19, 0x1379);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2e, 0x1475);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb3c, 0x87a0);
    _setUpActor(USER4);
        Target.step();
        _delay(0xff, 0xc543);
    _setUpActor(USER2);
        Target.step();
        _delay(0x46b47, 0x1320);
    _setUpActor(USER1);
        Target.step();
        _delay(0x66815, 0x87a0);
    _setUpActor(USER3);
        Target.step();
        _delay(0xfc62, 0x552);
    _setUpActor(USER3);
        Target.step();
        _delay(0x2a045, 0x1386);
    _setUpActor(USER4);
        Target.step();
        _delay(0x94ab, 0x1362);
    _setUpActor(USER3);
        Target.step();
        _delay(0x27, 0x2c55);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb3f, 0x135f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x582b0, 0x135e);
    _setUpActor(USER3);
        Target.step();
        _delay(0x663c, 0x27);
    _setUpActor(USER2);
        Target.step();
        _delay(0x7f7c2, 0x9248);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb43, 0x26ee);
    _setUpActor(USER2);
        Target.step();
        _delay(0xc247, 0x6);
    _setUpActor(USER3);
        Target.step();
        _delay(0xff, 0x14);
    _setUpActor(USER4);
        Target.step();
        _delay(0x12e1f, 0x43);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6123, 0x1362);
    _setUpActor(USER3);
        Target.step();
        _delay(0x41, 0x1376);
    _setUpActor(USER4);
        Target.step();
        _delay(0x462d5, 0xea96);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5408b, 0x2a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb32, 0xd273);
    _setUpActor(USER3);
        Target.step();
        _delay(0x2e, 0x1);
    _setUpActor(USER2);
        Target.step();
        _delay(0xf, 0x824d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6123, 0x40);
    _setUpActor(USER4);
        Target.step();
        _delay(0x63160, 0x755a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x712e4, 0x1378);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2b24c, 0xc543);
    _setUpActor(USER5);
        Target.step();
        _delay(0x75d98, 0x6);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb46, 0x5daa);
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
