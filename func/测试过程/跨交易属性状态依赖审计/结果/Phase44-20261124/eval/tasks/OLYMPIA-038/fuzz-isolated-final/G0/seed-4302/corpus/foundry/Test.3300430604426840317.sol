// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x20000);
    address constant USER4 = address(0x50000);
    address constant USER5 = address(0x30000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eaeb, 0x31e4);
    _setUpActor(USER1);
        Target.step();
        _delay(0x24b01, 0x3c09);
    _setUpActor(USER1);
        Target.step();
        _delay(0x214c8, 0x28);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5d, 0x24);
    _setUpActor(USER3);
        Target.step();
        _delay(0x5f467, 0x1355);
    _setUpActor(USER1);
        Target.step();
        _delay(0x3256a, 0x5f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2a045, 0x26c0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x212f1, 0x1343);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eaf6, 0xeb58);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5408b, 0x31);
    _setUpActor(USER2);
        Target.step();
        _delay(0x43af0, 0x1348);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8359f, 0x2c);
    _setUpActor(USER5);
        Target.step();
        _delay(0x34, 0xb);
    _setUpActor(USER5);
        Target.step();
        _delay(0x8, 0x1368);
    _setUpActor(USER2);
        Target.step();
        _delay(0xb, 0xd0cb);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb39, 0x58);
    _setUpActor(USER1);
        Target.step();
        _delay(0x433c2, 0x138d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x53, 0x1399);
    _setUpActor(USER1);
        Target.step();
        _delay(0xb, 0x5caa);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb18, 0x5);
    _setUpActor(USER2);
        Target.step();
        _delay(0x8f040, 0x138e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x65373, 0x5a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb3e, 0x3a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x13, 0x137d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2d, 0x963b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x17dd9, 0xe8a0);
    _setUpActor(USER4);
        Target.step();
        _delay(0x3e1ce, 0x4f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb12, 0x136d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x21, 0x38);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2fa33, 0x1374);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb15, 0x2c);
    _setUpActor(USER1);
        Target.step();
        _delay(0x714e6, 0x55);
    _setUpActor(USER1);
        Target.step();
        _delay(0x60, 0x57);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eae6, 0x440);
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
