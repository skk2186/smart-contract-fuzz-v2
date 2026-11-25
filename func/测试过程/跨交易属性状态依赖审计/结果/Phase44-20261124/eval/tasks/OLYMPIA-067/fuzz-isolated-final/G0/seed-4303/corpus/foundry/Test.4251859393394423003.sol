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
        _delay(0x4eadb, 0x89b0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x73, 0x133c);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eadb, 0x1329);
    _setUpActor(USER3);
        Target.step();
        _delay(0x711f5, 0x6b0c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x9d, 0xd3);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2, 0x1387);
    _setUpActor(USER2);
        Target.step();
        _delay(0x8e, 0x1340);
    _setUpActor(USER3);
        Target.step();
        _delay(0x51, 0xc09e);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb44, 0x1310);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4ea75, 0xebcc);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2e, 0x12e1);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb39, 0x1315);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb12, 0x8c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb04, 0x9c);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2fa33, 0x11d8);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eae0, 0x12e6);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6a9f7, 0x12cb);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4ea77, 0xda);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb1d, 0x30);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4daf5, 0xc0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x90fd7, 0x12c3);
    _setUpActor(USER5);
        Target.step();
        _delay(0xb9, 0x6d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb14, 0x16);
    _setUpActor(USER5);
        Target.step();
        _delay(0xa0, 0x1b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4ea7a, 0xa369);
    _setUpActor(USER4);
        Target.step();
        _delay(0x38, 0x43b8);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4ea81, 0xb3);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1f113, 0x1361);
    _setUpActor(USER3);
        Target.step();
        _delay(0x189e3, 0x619b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6d464, 0x29);
    _setUpActor(USER4);
        Target.step();
        _delay(0xffff, 0xd38b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x21, 0x12f4);
    _setUpActor(USER1);
        Target.step();
        _delay(0x81f7, 0x138a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eab9, 0x1343);
    _setUpActor(USER5);
        Target.step();
        _delay(0xac, 0x12f4);
    _setUpActor(USER4);
        Target.step();
        _delay(0x60, 0x8b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x767c4, 0x12dc);
    _setUpActor(USER4);
        Target.step();
        _delay(0x875e1, 0x1398);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb34, 0x12ea);
    _setUpActor(USER4);
        Target.step();
        _delay(0x74d9f, 0xad);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb26, 0xeb6b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eacc, 0x1365);
    _setUpActor(USER3);
        Target.step();
        _delay(0x912ed, 0x1383);
    _setUpActor(USER1);
        Target.step();
        _delay(0xb6, 0x12ee);
    _setUpActor(USER3);
        Target.step();
        _delay(0x95, 0xbe39);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4ea76, 0x12f5);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4ea9f, 0x2422);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb40, 0x7660);
    _setUpActor(USER3);
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
