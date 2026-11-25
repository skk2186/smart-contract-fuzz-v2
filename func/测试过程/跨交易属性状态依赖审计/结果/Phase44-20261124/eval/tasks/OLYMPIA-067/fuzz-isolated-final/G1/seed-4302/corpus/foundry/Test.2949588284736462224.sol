// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x50000);
    address constant USER5 = address(0x40000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eae2, 0x8d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x42655, 0x2057);
    _setUpActor(USER2);
        Target.step();
        _delay(0x47d79, 0xea4d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4ea7e, 0x5aeb);
    _setUpActor(USER2);
        Target.step();
        _delay(0xaf, 0x4ddd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x189e3, 0x3d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4ea93, 0xcfae);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4ea92, 0x7f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb23, 0x1375);
    _setUpActor(USER1);
        Target.step();
        _delay(0x77, 0x78);
    _setUpActor(USER1);
        Target.step();
        _delay(0xc7, 0x3c07);
    _setUpActor(USER5);
        Target.step();
        _delay(0x66, 0xe433);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eaa9, 0x1379);
    _setUpActor(USER2);
        Target.step();
        _delay(0x103ef, 0x133a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3, 0xb9);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eac1, 0x1414);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaa7, 0x136c);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3d, 0x2d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6b504, 0x12eb);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eab3, 0x1365);
    _setUpActor(USER1);
        Target.step();
        _delay(0x28928, 0x4d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x61189, 0x573c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x3256a, 0x55);
    _setUpActor(USER3);
        Target.step();
        _delay(0x83, 0x2d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x63720, 0x19);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eaee, 0x1315);
    _setUpActor(USER1);
        Target.step();
        _delay(0xa0, 0x9073);
    _setUpActor(USER4);
        Target.step();
        _delay(0x25, 0xeb6b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb30, 0x1337);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eadd, 0x32);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4ea9b, 0x2b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x65679, 0x1320);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6b504, 0x1307);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb22, 0x51);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2a86f, 0x9e);
    _setUpActor(USER1);
        Target.step();
        _delay(0xc9, 0xea7);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7ec5e, 0xd7);
    _setUpActor(USER5);
        Target.step();
        _delay(0xc5, 0x1364);
    _setUpActor(USER1);
        Target.step();
        _delay(0x59, 0x5caa);
    _setUpActor(USER5);
        Target.step();
        _delay(0x76ea6, 0x12d1);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eaee, 0x133f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x8af1a, 0xa663);
    _setUpActor(USER3);
        Target.step();
        _delay(0x87be4, 0x1);
    _setUpActor(USER1);
        Target.step();
        _delay(0x153e4, 0x12eb);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb0d, 0xe59f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x76a6f, 0x5e);
    _setUpActor(USER2);
        Target.step();
        _delay(0xca, 0x2ea6);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5bd20, 0x13be);
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
