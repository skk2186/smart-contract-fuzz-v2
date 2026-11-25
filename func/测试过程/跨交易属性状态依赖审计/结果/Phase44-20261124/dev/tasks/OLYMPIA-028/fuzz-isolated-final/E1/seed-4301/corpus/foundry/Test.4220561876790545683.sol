// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x30000);
    address constant USER2 = address(0x10000);
    address constant USER3 = address(0x20000);
    address constant USER4 = address(0x40000);
    address constant USER5 = address(0x50000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x63720, 0x90da);
    _setUpActor(USER2);
        Target.step();
        _delay(0x48, 0x9315);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb2b, 0xb7e3);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1f, 0x4ddd);
    _setUpActor(USER4);
        Target.step();
        _delay(0x13, 0x29);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7f7c2, 0x134d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x2621e, 0x619b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4e, 0x133f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x20, 0x137f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eaf2, 0x135c);
    _setUpActor(USER5);
        Target.step();
        _delay(0x90662, 0x13);
    _setUpActor(USER5);
        Target.step();
        _delay(0x59, 0x138e);
    _setUpActor(USER1);
        Target.step();
        _delay(0x142f0, 0x138c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8af1a, 0x38);
    _setUpActor(USER4);
        Target.step();
        _delay(0x36, 0x20);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb2e, 0xd1ae);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb0a, 0x2f7b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x66, 0x137d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eafa, 0xcf4e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb0f, 0x5b6b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x74d9f, 0x463);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eac7, 0x1375);
    _setUpActor(USER1);
        Target.step();
        _delay(0x15, 0x1344);
    _setUpActor(USER1);
        Target.step();
        _delay(0x103ef, 0x46);
    _setUpActor(USER1);
        Target.step();
        _delay(0x55, 0x381e);
    _setUpActor(USER3);
        Target.step();
        _delay(0x46b47, 0x47);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7f467, 0x1394);
    _setUpActor(USER1);
        Target.step();
        _delay(0x81f7, 0x138f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eae4, 0x1398);
    _setUpActor(USER2);
        Target.step();
        _delay(0x875e1, 0x60);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb44, 0x137e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x62b5f, 0x1379);
    _setUpActor(USER3);
        Target.step();
        _delay(0x35, 0x6);
    _setUpActor(USER4);
        Target.step();
        _delay(0x58, 0x95ce);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3c, 0x1cdd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eaf0, 0x1382);
    _setUpActor(USER5);
        Target.step();
        _delay(0x77bd0, 0xea96);
    _setUpActor(USER1);
        Target.step();
        _delay(0x9, 0x136d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8, 0x41);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb24, 0x1320);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2d, 0x1342);
    _setUpActor(USER1);
        Target.step();
        _delay(0x10978, 0x10);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eac7, 0x5aeb);
    _setUpActor(USER3);
        Target.step();
        _delay(0x46, 0xb31c);
    _setUpActor(USER5);
        Target.step();
        _setUpActor(USER4);
        Target.bug();
        _delay(0x79190, 0x92c7);
    _setUpActor(USER5);
        Target.step();
        _delay(0x77bce, 0x59);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4, 0x4a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x47b5, 0x1f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eac7, 0x44d6);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3f, 0x52);
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
