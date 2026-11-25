// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x10000);
    address constant USER3 = address(0x40000);
    address constant USER4 = address(0x50000);
    address constant USER5 = address(0x30000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x142ef, 0x12e6);
    _setUpActor(USER1);
        Target.step();
        _delay(0x28, 0x46);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eab8, 0xda);
    _setUpActor(USER3);
        Target.step();
        _delay(0x70, 0xce);
    _setUpActor(USER1);
        Target.step();
        _delay(0x712e4, 0x1351);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7cf9b, 0x88cf);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4ea8f, 0x1359);
    _setUpActor(USER3);
        Target.step();
        _delay(0x576ad, 0x2fea);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eac2, 0x1300);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6d, 0xe59f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4ea66, 0xd4);
    _setUpActor(USER5);
        Target.step();
        _delay(0xdd, 0x94b2);
    _setUpActor(USER1);
        Target.step();
        _delay(0xaa, 0xe1);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaef, 0xebcc);
    _setUpActor(USER3);
        Target.step();
        _delay(0x85b27, 0x12d3);
    _setUpActor(USER5);
        Target.step();
        _delay(0x2a, 0x1301);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1b, 0x1363);
    _setUpActor(USER5);
        Target.step();
        _delay(0xce, 0x130b);
    _setUpActor(USER2);
        Target.step();
        _delay(0xc4f1, 0xd6);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4ea78, 0x88);
    _setUpActor(USER1);
        Target.step();
        _delay(0x9d, 0x12c7);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4ea78, 0x135d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaa5, 0xba);
    _setUpActor(USER1);
        Target.step();
        _delay(0x9d, 0x1381);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eabf, 0x5ef7);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb19, 0x5a0b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1c, 0x12e5);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eaeb, 0x1302);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eabe, 0x12e8);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eafd, 0x50);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb03, 0x2ec3);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1a, 0x12e9);
    _setUpActor(USER5);
        Target.step();
        _delay(0xe2, 0x32);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4b, 0x132b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x48a23, 0x64ea);
    _setUpActor(USER1);
        Target.step();
        _delay(0x8388c, 0x9de);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eabf, 0xd5bd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eaf2, 0xff);
    _setUpActor(USER1);
        Target.step();
        _delay(0x8a317, 0xea96);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4ea99, 0xbf);
    _setUpActor(USER2);
        Target.step();
        _delay(0x24, 0x137f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eab1, 0x77);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eab8, 0x1371);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7b6a, 0x131b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x8a6c8, 0x8e45);
    _setUpActor(USER2);
        Target.step();
        _delay(0x9d, 0x69);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1f, 0x1322);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2bf4, 0x2c);
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
