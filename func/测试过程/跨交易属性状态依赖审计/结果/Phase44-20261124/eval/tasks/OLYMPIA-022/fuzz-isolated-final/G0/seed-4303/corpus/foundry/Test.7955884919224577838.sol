// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x50000);
    address constant USER3 = address(0x20000);
    address constant USER4 = address(0x30000);
    address constant USER5 = address(0x10000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eb2f, 0x7660);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4a0f1, 0xa4f5);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4, 0x3032);
    _setUpActor(USER3);
        Target.step();
        _delay(0x136fe, 0xe8a0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb38, 0x619b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x37272, 0x2b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7cf4e, 0x5184);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6c82f, 0x1);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb3b, 0x13be);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb42, 0x1b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4daf5, 0x3032);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7f, 0x7840);
    _setUpActor(USER2);
        Target.step();
        _delay(0x570be, 0x12);
    _setUpActor(USER2);
        Target.step();
        _delay(0x28928, 0x4f13);
    _setUpActor(USER1);
        Target.step();
        _delay(0x85b27, 0xdefe);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6, 0x87a0);
    _setUpActor(USER4);
        Target.step();
        _setUpActor(USER5);
        Target.step();
        _delay(0x14, 0x18);
    _setUpActor(USER1);
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
