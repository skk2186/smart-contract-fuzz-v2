// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x40000);
    address constant USER4 = address(0x10000);
    address constant USER5 = address(0x50000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x3d, 0xb2fb);
    _setUpActor(USER1);
        Target.step();
        _delay(0xa, 0x1375);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5408b, 0x40);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb45, 0x3);
    _setUpActor(USER2);
        Target.step();
        _delay(0x8, 0x3c09);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4f26e, 0x755a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x80772, 0x5c65);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6b504, 0x2c);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb2c, 0x6689);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8, 0x28);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6123, 0xb556);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5f467, 0xa4f5);
    _setUpActor(USER1);
        Target.step();
        _delay(0x48a23, 0xb2fb);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6a9f7, 0x7887);
    _setUpActor(USER1);
        Target.step();
        _delay(0x329b9, 0x17);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb33, 0x139d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x75d98, 0x2ea6);
    _setUpActor(USER2);
        Target.step();
        _delay(0x72455, 0x185a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x42655, 0x1361);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb08, 0xb2fb);
    _setUpActor(USER5);
        Target.step();
        _delay(0x576ad, 0x89b0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x15, 0xf8e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x45832, 0x7840);
    _setUpActor(USER1);
        Target.step();
        _delay(0x80772, 0x1393);
    _setUpActor(USER5);
        Target.step();
        _delay(0x9, 0x1362);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb19, 0x5b6b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x475d0, 0x82f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb38, 0x5daa);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1b73c, 0x1398);
    _setUpActor(USER5);
        Target.step();
        _delay(0x43, 0x1320);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb1d, 0x6b0c);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5, 0xba8f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x580b0, 0x1363);
    _setUpActor(USER4);
        Target.step();
        _delay(0x80772, 0x619b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb37, 0x107f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7f, 0x9d0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x8f9df, 0x1389);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6a2ce, 0x5aeb);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb08, 0x10);
    _setUpActor(USER4);
        Target.step();
        _delay(0xd, 0x2a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4, 0x135d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb40, 0x25e6);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb07, 0x13bd);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1c18d, 0xcf13);
    _setUpActor(USER5);
        Target.step();
        _delay(0x1b, 0xd8f2);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8f9df, 0x13bd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x43, 0xb556);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3d, 0x1);
    _setUpActor(USER2);
        Target.step();
        _delay(0x28, 0x1395);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb30, 0x1395);
    _setUpActor(USER1);
        Target.step();
        _delay(0x19, 0x7);
    _setUpActor(USER3);
        Target.step();
        _delay(0x76ea6, 0xc543);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8f9df, 0x139a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x28928, 0x107f);
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
