// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x50000);
    address constant USER4 = address(0x40000);
    address constant USER5 = address(0x20000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eb31, 0x2e81);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb0a, 0x17);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1c5dc, 0x1389);
    _setUpActor(USER1);
        Target.step();
        _delay(0x13, 0x1362);
    _setUpActor(USER1);
        Target.step();
        _delay(0x329b9, 0xff);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb45, 0x1392);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb1a, 0x3f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x52be8, 0x1387);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb06, 0x3);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb30, 0x1390);
    _setUpActor(USER3);
        Target.step();
        _delay(0x103a1, 0xc2a7);
    _setUpActor(USER3);
        Target.step();
        _delay(0x17, 0x2f15);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb35, 0xb556);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3f, 0x5daa);
    _setUpActor(USER2);
        Target.step();
        _delay(0xb056, 0xa);
    _setUpActor(USER4);
        Target.step();
        _delay(0x42, 0x107f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb36, 0xea4e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x62123, 0xe4d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x804a4, 0xd0cb);
    _setUpActor(USER1);
        Target.step();
        _delay(0x62a00, 0x6b0c);
    _setUpActor(USER5);
        Target.step();
        _delay(0x19, 0xd8f2);
    _setUpActor(USER3);
        Target.step();
        _delay(0x43af0, 0xe4d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x24b01, 0x6);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb45, 0x4ddd);
    _setUpActor(USER5);
        Target.step();
        _delay(0x712e3, 0x94d4);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2a045, 0x47fd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x42655, 0x320);
    _setUpActor(USER1);
        Target.step();
        _delay(0x214ca, 0x1372);
    _setUpActor(USER5);
        Target.step();
        _delay(0x77bd0, 0xd743);
    _setUpActor(USER2);
        Target.step();
        _delay(0x549c9, 0x16);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2fa33, 0x185a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x29, 0x8ffb);
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
