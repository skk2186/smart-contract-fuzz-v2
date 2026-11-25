// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x30000);
    address constant USER5 = address(0x50000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x6a9f7, 0xeb6b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x19, 0x1474);
    _setUpActor(USER2);
        Target.step();
        _setUpActor(USER1);
        Target.step();
        _delay(0x3e301, 0x2f5);
    _setUpActor(USER3);
        Target.step();
        _delay(0x64ad5, 0xf);
    _setUpActor(USER4);
        Target.step();
        _delay(0x3340a, 0x8);
    _setUpActor(USER3);
        Target.step();
        _delay(0x5c7af, 0x8980);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6ae4e, 0x1320);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb34, 0xcda9);
    _setUpActor(USER3);
        Target.step();
        _delay(0xc4f1, 0x1c9b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x85b27, 0x26ed);
    _setUpActor(USER1);
        Target.step();
        _setUpActor(USER3);
        Target.step();
        _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2e, 0xdefe);
    _setUpActor(USER5);
        Target.step();
        _delay(0xc, 0x824d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb3a, 0x824d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x42655, 0x552);
    _setUpActor(USER3);
        Target.step();
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
