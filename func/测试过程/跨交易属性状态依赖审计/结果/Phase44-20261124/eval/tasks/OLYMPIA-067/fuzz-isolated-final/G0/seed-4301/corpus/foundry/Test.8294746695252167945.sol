// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x10000);
    address constant USER3 = address(0x30000);
    address constant USER4 = address(0x20000);
    address constant USER5 = address(0x50000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eb11, 0xa4);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1b2da, 0x5b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eae5, 0x7ba8);
    _setUpActor(USER3);
        Target.step();
        _delay(0x51, 0x12e3);
    _setUpActor(USER4);
        Target.step();
        _delay(0xffff, 0xd8f2);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaf6, 0x9d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x97, 0xe0);
    _setUpActor(USER4);
        Target.step();
        _delay(0x62, 0x14);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eaa2, 0x131b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6b721, 0xa2);
    _setUpActor(USER2);
        Target.step();
        _delay(0xc4, 0xdc);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4ead8, 0x888f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4d, 0x7c);
    _setUpActor(USER2);
        Target.step();
        _delay(0xb1, 0x7d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb3a, 0xd5);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4ea66, 0x131b);
    _setUpActor(USER5);
        Target.step();
        _delay(0xb6, 0x138e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x65373, 0x12c6);
    _setUpActor(USER2);
        Target.step();
        _delay(0x81, 0x12c6);
    _setUpActor(USER4);
        Target.step();
        _delay(0x62e05, 0x1379);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7f467, 0x1317);
    _setUpActor(USER4);
        Target.step();
        _delay(0x99, 0x1348);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4ea9e, 0xc543);
    _setUpActor(USER5);
        Target.step();
        _delay(0xc247, 0x88);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaaa, 0x4b44);
    _setUpActor(USER3);
        Target.step();
        _delay(0xa, 0x134c);
    _setUpActor(USER5);
        Target.step();
        _delay(0xd8, 0xdb37);
    _setUpActor(USER1);
        Target.bug();
        _delay(0x4eaa9, 0x6b03);
    _setUpActor(USER5);
        Target.step();
        _delay(0x2e, 0x1324);
    _setUpActor(USER2);
        Target.step();
        _delay(0x26, 0xa0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x8af1a, 0xb7);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eade, 0x92);
    _setUpActor(USER1);
        Target.step();
        _delay(0xba, 0x32);
    _setUpActor(USER3);
        Target.step();
        _delay(0x13, 0x136d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x65410, 0x70);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3f, 0x9d0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4ea66, 0x138d);
    _setUpActor(USER2);
        Target.step();
        _delay(0xb8, 0x138f);
    _setUpActor(USER2);
        Target.step();
        _delay(0xe3, 0x1317);
    _setUpActor(USER5);
        Target.step();
        _delay(0xe2, 0x12f6);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7f, 0x9a);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eaca, 0xa1);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2, 0x132f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x13, 0x12da);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3c, 0x1319);
    _setUpActor(USER4);
        Target.step();
        _delay(0x87, 0x4f13);
    _setUpActor(USER5);
        Target.step();
        _delay(0x6a, 0x12e8);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eaeb, 0x2f);
    _setUpActor(USER4);
        Target.step();
        _delay(0xa2, 0x4);
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
