// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x10000);
    address constant USER3 = address(0x50000);
    address constant USER4 = address(0x40000);
    address constant USER5 = address(0x30000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x2a6f7, 0x5aeb);
    _setUpActor(USER1);
        Target.step();
        _delay(0x65679, 0x119f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x42655, 0x26c0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb35, 0x9c1);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1, 0x2f15);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb3e, 0x89b0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3340a, 0x2);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6123, 0xc);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6c82f, 0x26c0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x15, 0x753b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb3e, 0x18);
    _setUpActor(USER3);
        Target.step();
        _delay(0x307c6, 0x4f13);
    _setUpActor(USER1);
        Target.step();
        _delay(0x63160, 0x3032);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb35, 0x5c65);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb1b, 0x4f13);
    _setUpActor(USER3);
        Target.step();
        _delay(0x2a, 0xe4d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb37, 0x1372);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6792, 0x20ff);
    _setUpActor(USER3);
        Target.step();
        _delay(0x94ab, 0x1387);
    _setUpActor(USER4);
        Target.step();
        _delay(0x875e1, 0x1d57);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4, 0x4ddd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x804a4, 0x7c0);
    _setUpActor(USER4);
        Target.step();
        _delay(0x12, 0x94d4);
    _setUpActor(USER1);
        Target.step();
        _delay(0x24b01, 0xea4e);
    _setUpActor(USER1);
        Target.step();
        _delay(0xb, 0xc9fe);
    _setUpActor(USER1);
        Target.step();
        _delay(0x433c2, 0x7f);
    _setUpActor(USER2);
        Target.step();
        _delay(0x62e05, 0xa475);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6b617, 0x138e);
    _setUpActor(USER1);
        Target.step();
        _delay(0x20ee0, 0x1c9b);
    _setUpActor(USER5);
        Target.step();
        _delay(0xffff, 0x5ef7);
    _setUpActor(USER3);
        Target.step();
        _delay(0x29, 0x1391);
    _setUpActor(USER1);
        Target.step();
        _delay(0x94ab, 0x2e32);
    _setUpActor(USER5);
        Target.step();
        _delay(0x2a, 0x26c0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x214c9, 0x320);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb19, 0x2e81);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1, 0x95ce);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2621e, 0x1375);
    _setUpActor(USER1);
        Target.step();
        _delay(0xe, 0x1a41);
    _setUpActor(USER5);
        Target.step();
        _delay(0x142ee, 0xd149);
    _setUpActor(USER5);
        Target.step();
        _delay(0xb056, 0x9);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb2e, 0x6);
    _setUpActor(USER2);
        Target.step();
        _delay(0x142ee, 0x3032);
    _setUpActor(USER3);
        Target.step();
        _delay(0x11, 0x1385);
    _setUpActor(USER5);
        Target.step();
        _delay(0x804a4, 0x139e);
    _setUpActor(USER5);
        Target.step();
        _delay(0x1a, 0x3c09);
    _setUpActor(USER2);
        Target.step();
        _delay(0x8f9df, 0x12);
    _setUpActor(USER5);
        Target.step();
        _delay(0x77bce, 0xb31c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x94ab, 0x138b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1b2da, 0x26c0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x142f0, 0x7c0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x307c6, 0x19);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb41, 0x7fe1);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7f, 0x26c0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb41, 0xea4f);
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
