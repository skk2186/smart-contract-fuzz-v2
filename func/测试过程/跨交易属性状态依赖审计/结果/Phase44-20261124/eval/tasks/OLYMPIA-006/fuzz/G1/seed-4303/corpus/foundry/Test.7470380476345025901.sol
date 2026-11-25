// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x50000);
    address constant USER4 = address(0x20000);
    address constant USER5 = address(0x40000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x19, 0x1396);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1, 0xb0cd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4a9a4, 0x2e32);
    _setUpActor(USER2);
        Target.step();
        _delay(0x13, 0x3c07);
    _setUpActor(USER3);
        Target.step();
        _delay(0x103ef, 0xf);
    _setUpActor(USER3);
        Target.step();
        _delay(0x5408b, 0x2d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x77bd0, 0x1397);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb32, 0x13f0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3340a, 0x463);
    _setUpActor(USER5);
        Target.step();
        _delay(0x1c18d, 0x1390);
    _setUpActor(USER2);
        Target.step();
        _delay(0x7443d, 0x7f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb3b, 0xe4a7);
    _setUpActor(USER2);
        Target.step();
        _delay(0x7f, 0x440);
    _setUpActor(USER5);
        Target.step();
        _delay(0x3340a, 0xeb6b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x52be8, 0xc132);
    _setUpActor(USER1);
        Target.step();
        _delay(0x214c9, 0xf);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb20, 0x26ee);
    _setUpActor(USER5);
        Target.step();
        _delay(0x14, 0x1475);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2a045, 0x47fd);
    _setUpActor(USER5);
        Target.step();
        _delay(0x212f1, 0x14);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6d828, 0x1375);
    _setUpActor(USER2);
        Target.step();
        _delay(0x42655, 0x5caa);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2e, 0xb556);
    _setUpActor(USER1);
        Target.step();
        _delay(0x76ea6, 0x1b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x43af0, 0x9);
    _setUpActor(USER1);
        Target.step();
        _delay(0x16, 0x138e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb37, 0x30cd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x627fd, 0x28);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7, 0x231);
    _setUpActor(USER5);
        Target.step();
        _delay(0x433c2, 0x138d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x142ef, 0x3c07);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6ae4e, 0x1372);
    _setUpActor(USER1);
        Target.step();
        _delay(0x14, 0x1378);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb3f, 0xe8a0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x62e05, 0x1393);
    _setUpActor(USER3);
        Target.step();
        _delay(0x27, 0x597d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x214c9, 0xb14);
    _setUpActor(USER5);
        Target.step();
        _delay(0x27cbf, 0xb31c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2a045, 0x1a41);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8af1a, 0x3c07);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5caa0, 0x2f15);
    _setUpActor(USER3);
        Target.step();
        _delay(0x66815, 0x139b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7b6a, 0x107f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6, 0xcfae);
    _setUpActor(USER4);
        Target.step();
        _delay(0x10978, 0x2b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x582b0, 0xea4e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x24b01, 0x1385);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8, 0x2b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x13, 0x19);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1c18d, 0x2c55);
    _setUpActor(USER5);
        Target.step();
        _delay(0x533aa, 0x47fd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x92b1f, 0x7c0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x10978, 0x9d0);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb1b, 0x47fd);
    _setUpActor(USER2);
        Target.step();
        _delay(0xb056, 0x824d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5408b, 0x1395);
    _setUpActor(USER3);
        Target.step();
        _delay(0x66815, 0x440);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb2f, 0x1374);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5caa0, 0xa4f5);
    _setUpActor(USER5);
        Target.step();
        _delay(0x712e4, 0x138f);
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
