// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x30000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x20000);
    address constant USER5 = address(0x50000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eb2d, 0x2422);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7f, 0x1388);
    _setUpActor(USER3);
        Target.step();
        _delay(0x215c1, 0x4f13);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb42, 0x320);
    _setUpActor(USER3);
        Target.step();
        _delay(0x77bd0, 0x6);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb37, 0x185a);
    _setUpActor(USER5);
        Target.step();
        _delay(0x63160, 0x2c55);
    _setUpActor(USER3);
        Target.step();
        _delay(0x214ca, 0xdefe);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5f467, 0x8ffb);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1b2da, 0x1389);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb35, 0x1b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3, 0x1393);
    _setUpActor(USER2);
        Target.step();
        _delay(0x37702, 0x1397);
    _setUpActor(USER5);
        Target.step();
        _delay(0x46b47, 0xb2fb);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb41, 0x619b);
    _setUpActor(USER4);
        Target.step();
        _delay(0xc, 0xd0cb);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1cae0, 0x1740);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7d68b, 0xd8f2);
    _setUpActor(USER2);
        Target.step();
        _delay(0x46b47, 0x12);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb42, 0x1389);
    _setUpActor(USER5);
        Target.step();
        _delay(0x48a23, 0x107f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x28928, 0xe59f);
    _setUpActor(USER2);
        Target.step();
        _delay(0xc4f1, 0xea4f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x10, 0x139a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4cc2a, 0x552);
    _setUpActor(USER2);
        Target.step();
        _delay(0xff, 0x7424);
    _setUpActor(USER1);
        Target.step();
        _delay(0x65410, 0x8);
    _setUpActor(USER4);
        Target.step();
        _delay(0x10059, 0x91bb);
    _setUpActor(USER1);
        Target.step();
        _delay(0x640ef, 0x94d4);
    _setUpActor(USER2);
        Target.step();
        _delay(0x804a4, 0x5b6b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x10978, 0xbaad);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7eea7, 0x552);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7cf4e, 0x9d0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x3066, 0x122);
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
