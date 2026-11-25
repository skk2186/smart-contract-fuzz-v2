// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x20000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x50000);
    address constant USER5 = address(0x30000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eaf4, 0x231);
    _setUpActor(USER1);
        Target.step();
        _delay(0x28928, 0xd13a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6166e, 0x134c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eae5, 0x1396);
    _setUpActor(USER2);
        Target.step();
        _delay(0xf, 0xd0cb);
    _setUpActor(USER5);
        Target.step();
        _delay(0x62, 0xb2fb);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1cae0, 0x47);
    _setUpActor(USER1);
        Target.step();
        _delay(0x77bce, 0x20);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb33, 0x62);
    _setUpActor(USER1);
        Target.step();
        _delay(0x43, 0x1357);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaf6, 0x597d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x78be0, 0xeb20);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7eea7, 0xf);
    _setUpActor(USER5);
        Target.step();
        _delay(0x214c9, 0x138c);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb39, 0x133b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb01, 0x68b4);
    _setUpActor(USER1);
        Target.step();
        _delay(0x62, 0x7fe1);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb39, 0x5d4d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb1b, 0x755a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3a, 0x31);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb05, 0xd1ae);
    _setUpActor(USER4);
        Target.step();
        _delay(0x61e55, 0x15);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4694f, 0xd065);
    _setUpActor(USER5);
        Target.step();
        _delay(0x51251, 0x1740);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3340a, 0x38);
    _setUpActor(USER2);
        Target.step();
        _delay(0x49, 0x29);
    _setUpActor(USER1);
        Target.step();
        _delay(0x74d9f, 0x135e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x712e3, 0x5d);
    _setUpActor(USER1);
        Target.step();
        _delay(0xffff, 0xea35);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eaf8, 0x46);
    _setUpActor(USER3);
        Target.step();
        _delay(0x668ee, 0x28);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4daf5, 0x137c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1eda4, 0x5);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1, 0x4c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1d, 0x134f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eaf4, 0x17);
    _setUpActor(USER1);
        Target.step();
        _delay(0x62e05, 0xb);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb05, 0x137a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eaee, 0x1d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb41, 0x133a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eaeb, 0x30cd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb1a, 0x7660);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7f7c2, 0xea4f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x60, 0x9e96);
    _setUpActor(USER5);
        Target.step();
        _delay(0x46, 0x4d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1c18d, 0x1369);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb26, 0x1367);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb3d, 0x20);
    _setUpActor(USER1);
        Target.step();
        _delay(0x42655, 0xcf13);
    _setUpActor(USER3);
        Target.step();
        _delay(0x62123, 0x1347);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb0b, 0x136d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5, 0x139f);
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
