// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x50000);
    address constant USER4 = address(0x20000);
    address constant USER5 = address(0x10000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x42, 0x4ddd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x75d98, 0x753b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2d, 0x139f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8, 0x5daa);
    _setUpActor(USER5);
        Target.step();
        _delay(0x2a, 0xd619);
    _setUpActor(USER4);
        Target.step();
        _delay(0x41a2, 0x3a9d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x16, 0x1a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6123, 0x43);
    _setUpActor(USER1);
        Target.step();
        _delay(0x27, 0x8685);
    _setUpActor(USER5);
        Target.step();
        _delay(0x14, 0x47fd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1b2da, 0x1399);
    _setUpActor(USER4);
        Target.step();
        _delay(0xd, 0xf);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb44, 0x139c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x16, 0xc107);
    _setUpActor(USER1);
        Target.step();
        _delay(0x523e3, 0xd619);
    _setUpActor(USER5);
        Target.step();
        _delay(0x307c6, 0x5);
    _setUpActor(USER2);
        Target.step();
        _delay(0x712e3, 0x3c09);
    _setUpActor(USER4);
        Target.step();
        _delay(0x17, 0x89b0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb05, 0x139e);
    _setUpActor(USER3);
        Target.step();
        _delay(0x85b27, 0xd065);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb2d, 0x1360);
    _setUpActor(USER4);
        Target.step();
        _delay(0x52be8, 0x58ab);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6b721, 0x89b0);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb34, 0xc107);
    _setUpActor(USER4);
        Target.step();
        _delay(0x189e3, 0x6b0c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3c, 0xd1cd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb1a, 0x2e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2c, 0xb0cd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb3b, 0x79a4);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb3b, 0x1362);
    _setUpActor(USER3);
        Target.step();
        _delay(0xe, 0xd8f2);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6c82f, 0x1a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb1b, 0x1391);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1051, 0x1397);
    _setUpActor(USER4);
        Target.step();
        _delay(0x62e05, 0x1394);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3e, 0x135d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x51251, 0x87a0);
    _setUpActor(USER2);
        Target.step();
        _delay(0xe, 0x3a32);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4a0f1, 0x15);
    _setUpActor(USER3);
        Target.step();
        _delay(0x81f7, 0x1362);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb1d, 0x27);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb33, 0x1394);
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
