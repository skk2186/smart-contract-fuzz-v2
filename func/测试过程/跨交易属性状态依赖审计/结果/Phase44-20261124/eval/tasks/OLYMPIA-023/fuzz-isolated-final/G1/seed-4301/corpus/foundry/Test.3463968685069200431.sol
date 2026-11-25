// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x30000);
    address constant USER2 = address(0x20000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x40000);
    address constant USER5 = address(0x50000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x76ea6, 0x10);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1051, 0xeb6b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6a2ce, 0x440);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1c5dc, 0x6b0c);
    _setUpActor(USER5);
        Target.step();
        _delay(0x38a20, 0x26ee);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5caa0, 0xd8f2);
    _setUpActor(USER2);
        Target.step();
        _delay(0x8345, 0x10);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4daf5, 0x992a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x74d9f, 0x89b0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7f467, 0x8);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb36, 0x7a00);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb3e, 0x1475);
    _setUpActor(USER2);
        Target.step();
        _delay(0x142ee, 0x7fe1);
    _setUpActor(USER3);
        Target.step();
        _delay(0x142ef, 0x1392);
    _setUpActor(USER1);
        Target.step();
        _delay(0xa, 0x138f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x699e2, 0x7802);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5bd20, 0xa372);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb40, 0x26c0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6b504, 0xb9f9);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6e277, 0x488e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x75d98, 0x320);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb38, 0x138a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x668ee, 0x47fd);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4a55, 0xcf13);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1c18d, 0x6b0c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb46, 0x7);
    _setUpActor(USER5);
        Target.step();
        _delay(0x3256a, 0x2b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x81101, 0xcfae);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1b2da, 0x1);
    _setUpActor(USER4);
        Target.step();
        _delay(0x74d9f, 0x6);
    _setUpActor(USER5);
        Target.step();
        _delay(0x28928, 0xb31c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1f83a, 0x2e);
    _setUpActor(USER5);
        Target.step();
        _delay(0x212f1, 0x58ab);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8a317, 0x138f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb3e, 0x139d);
    _setUpActor(USER4);
        Target.step();
        _delay(0xffff, 0x1374);
    _setUpActor(USER3);
        Target.step();
        _delay(0x10, 0x7aa7);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5ac39, 0x20);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb1a, 0xb);
    _setUpActor(USER5);
        Target.step();
        _delay(0x5ab31, 0x3c08);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1cae0, 0x7840);
    _setUpActor(USER2);
        Target.step();
        _delay(0xd99, 0x231);
    _setUpActor(USER1);
        Target.step();
        _delay(0x19, 0x1387);
    _setUpActor(USER5);
        Target.step();
        _delay(0x2621e, 0x85e0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x63160, 0x20ff);
    _setUpActor(USER4);
        Target.step();
        _delay(0x56090, 0x9de);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb45, 0xc543);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb3a, 0x7);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb45, 0xd38b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7fff, 0xd0cb);
    _setUpActor(USER5);
        Target.step();
        _delay(0xa, 0x7a00);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb45, 0x8bd6);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb43, 0x3032);
    _setUpActor(USER5);
        Target.step();
        _delay(0xe, 0x753b);
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
