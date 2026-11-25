// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x50000);
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
        _delay(0x2d, 0x552);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7b6a, 0xc);
    _setUpActor(USER2);
        Target.step();
        _setUpActor(USER2);
        Target.step();
        _delay(0x2d, 0x139f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb1b, 0x37fa);
    _setUpActor(USER1);
        Target.step();
        _delay(0x17, 0x1377);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb30, 0xa663);
    _setUpActor(USER2);
        Target.step();
        _delay(0xff, 0x2c55);
    _setUpActor(USER3);
        Target.step();
        _delay(0x43af0, 0x85e0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x1b2da, 0x27);
    _setUpActor(USER4);
        Target.step();
        _delay(0x85b27, 0xebcc);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6b504, 0x8980);
    _setUpActor(USER4);
        Target.step();
        _delay(0x13, 0xdefe);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2a, 0x5d4d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x3256a, 0x9c1);
    _setUpActor(USER3);
        Target.step();
        _delay(0x21cd9, 0xb2ad);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4, 0x19);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb2d, 0x3c07);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5caa0, 0xea4e);
    _setUpActor(USER3);
        Target.step();
        _delay(0xc247, 0x1396);
    _setUpActor(USER2);
        Target.step();
        _delay(0x91b24, 0x7);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6ae4e, 0x27);
    _setUpActor(USER2);
        Target.step();
        _delay(0xc247, 0xea4f);
    _setUpActor(USER3);
        Target.step();
        _setUpActor(USER3);
        Target.step();
        _delay(0x6b721, 0x6e37);
    _setUpActor(USER5);
        Target.step();
        _delay(0x433c2, 0x139b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x433c2, 0x8980);
    _setUpActor(USER2);
        Target.step();
        _delay(0x13, 0xd065);
    _setUpActor(USER2);
        Target.step();
        _delay(0x74d9f, 0x1379);
    _setUpActor(USER4);
        Target.step();
        _delay(0x712e4, 0x5daa);
    _setUpActor(USER4);
        Target.step();
        _delay(0x74d9f, 0x58ab);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2fa33, 0x139e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1f113, 0x2e);
    _setUpActor(USER2);
        Target.step();
        _delay(0xff, 0x5b6b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8a317, 0x139c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb2c, 0x12);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb38, 0x1388);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2c, 0x7a00);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4, 0x1a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x13, 0xb0cd);
    _setUpActor(USER3);
        Target.step();
        _delay(0x77bd0, 0x1320);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb42, 0x26ee);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6fcba, 0x320);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8cc, 0x27);
    _setUpActor(USER1);
        Target.step();
        _delay(0x894e8, 0xda65);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1b2da, 0xe59f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x65679, 0x1396);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2c, 0xe8a0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x580b0, 0x11);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb44, 0x99ca);
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
