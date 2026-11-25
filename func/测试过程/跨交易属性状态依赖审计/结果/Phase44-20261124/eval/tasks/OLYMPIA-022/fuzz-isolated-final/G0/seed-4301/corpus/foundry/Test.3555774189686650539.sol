// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x50000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x30000);
    address constant USER4 = address(0x10000);
    address constant USER5 = address(0x20000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x14, 0x29);
    _setUpActor(USER1);
        Target.step();
        _delay(0x307c6, 0x5caa);
    _setUpActor(USER2);
        Target.step();
        _delay(0x10, 0x5daa);
    _setUpActor(USER3);
        Target.step();
        _delay(0x61e55, 0x2e32);
    _setUpActor(USER4);
        Target.step();
        _delay(0x75d98, 0xb2fb);
    _setUpActor(USER3);
        Target.step();
        _delay(0x63f38, 0xb2fb);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2f, 0x1376);
    _setUpActor(USER3);
        Target.step();
        _delay(0x27, 0x1375);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6b721, 0x1395);
    _setUpActor(USER2);
        Target.step();
        _delay(0x29, 0x7c0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6a9f7, 0x138f);
    _setUpActor(USER4);
        Target.step();
        _setUpActor(USER4);
        Target.step();
        _delay(0x4eb30, 0x1389);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1b73c, 0xff);
    _setUpActor(USER5);
        Target.step();
        _delay(0xd13, 0x15ee);
    _setUpActor(USER3);
        Target.step();
        _delay(0x5408b, 0xc3d1);
    _setUpActor(USER3);
        Target.step();
        _delay(0x62123, 0xd8af);
    _setUpActor(USER1);
        Target.step();
        _delay(0xc247, 0x1c9b);
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
