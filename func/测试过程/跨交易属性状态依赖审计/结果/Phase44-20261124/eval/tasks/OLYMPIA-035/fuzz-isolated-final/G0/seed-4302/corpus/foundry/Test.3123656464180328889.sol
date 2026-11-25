// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x30000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x20000);
    address constant USER4 = address(0x10000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x23, 0x4a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2fa33, 0x53);
    _setUpActor(USER3);
        Target.step();
        _delay(0x712e4, 0x1358);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb01, 0x185a);
    _setUpActor(USER1);
        Target.step();
        _setUpActor(USER4);
        Target.step();
        _delay(0x4eb1f, 0xa663);
    _setUpActor(USER3);
        Target.step();
        _delay(0x75d98, 0x1353);
    _setUpActor(USER4);
        Target.step();
        _delay(0x65373, 0x4f13);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb3d, 0x5f);
    _setUpActor(USER2);
        Target.step();
        _delay(0x33210, 0x1a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaf9, 0x18);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6bb23, 0x1391);
    _setUpActor(USER1);
        Target.step();
        _delay(0xb, 0x182b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x94ab, 0x89b0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eae1, 0x1365);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb0c, 0x5c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x142ee, 0x42);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb31, 0x137d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb0a, 0x1383);
    _setUpActor(USER1);
        Target.step();
        _setUpActor(USER4);
        Target.step();
        _delay(0x87c1a, 0x33);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaf5, 0x619b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x3a, 0x46ae);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaf1, 0x1364);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4a, 0x1346);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2f, 0x1345);
    _setUpActor(USER3);
        Target.step();
        _setUpActor(USER2);
        Target.step();
        _delay(0x305d6, 0x1381);
    _setUpActor(USER2);
        Target.step();
        _delay(0xb2e1, 0x24);
    _setUpActor(USER3);
        Target.step();
        _setUpActor(USER4);
        Target.step();
        _delay(0x4eaea, 0x16);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6123, 0x1392);
    _setUpActor(USER4);
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
