// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x50000);
    address constant USER2 = address(0x20000);
    address constant USER3 = address(0x40000);
    address constant USER4 = address(0x30000);
    address constant USER5 = address(0x10000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eae5, 0x1);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb26, 0xd0cb);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3ed2, 0x38);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2d, 0x134e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1b73c, 0xebcc);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb0a, 0xd0cb);
    _setUpActor(USER5);
        Target.step();
        _delay(0x2f, 0x116e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x142ef, 0x7f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x51251, 0x1391);
    _setUpActor(USER4);
        Target.step();
        _delay(0x11d50, 0x27);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1cae0, 0x1367);
    _setUpActor(USER5);
        Target.step();
        _delay(0x8c4eb, 0xea4d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x63160, 0x14);
    _setUpActor(USER5);
        Target.step();
        _delay(0x62123, 0x11);
    _setUpActor(USER1);
        Target.step();
        _delay(0x66, 0x3ed9);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7f7c2, 0x1384);
    _setUpActor(USER1);
        Target.step();
        _delay(0x433c2, 0xb31c);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb31, 0x138d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x51251, 0x29);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb34, 0x1369);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb14, 0x1358);
    _setUpActor(USER5);
        Target.step();
        _delay(0x66815, 0x7f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x214c8, 0x1348);
    _setUpActor(USER5);
        Target.step();
        _delay(0x85c8a, 0x94d4);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2, 0x7c0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x63, 0x1350);
    _setUpActor(USER1);
        Target.step();
        _delay(0xa, 0x89b0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x74d9f, 0x87a0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x103ef, 0x59bd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb28, 0x2c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x49, 0xebcc);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb46, 0x2f15);
    _setUpActor(USER5);
        Target.step();
        _delay(0x1e302, 0xd);
    _setUpActor(USER3);
        Target.step();
        _delay(0x5f467, 0x4);
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
