// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x50000);
    address constant USER4 = address(0x40000);
    address constant USER5 = address(0x20000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x87, 0x12c5);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb0f, 0xebcc);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb36, 0x32);
    _setUpActor(USER1);
        Target.step();
        _delay(0x76737, 0x83);
    _setUpActor(USER2);
        Target.step();
        _delay(0x11, 0xa5b2);
    _setUpActor(USER2);
        Target.step();
        _delay(0x42655, 0x1398);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3b, 0x136a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4ea79, 0x1388);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4ea79, 0x320);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4ea92, 0x4c);
    _setUpActor(USER5);
        Target.step();
        _delay(0x77bd0, 0xe59f);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1d, 0x137d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4ea75, 0x8f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x3, 0x99);
    _setUpActor(USER3);
        Target.step();
        _delay(0x85b27, 0x132b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x41a2, 0xcd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4ea7e, 0x135d);
    _setUpActor(USER2);
        Target.step();
        _delay(0xab, 0x8c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4a0f1, 0x1348);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eaf7, 0x51);
    _setUpActor(USER1);
        Target.step();
        _delay(0x24, 0x1385);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4ea73, 0x50);
    _setUpActor(USER3);
        Target.step();
        _delay(0x5e, 0x20);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1e, 0x3d6);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaa9, 0xb0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaf8, 0x6f);
    _setUpActor(USER1);
        Target.step();
        _delay(0xca, 0x12c5);
    _setUpActor(USER5);
        Target.step();
        _delay(0xc0, 0x132b);
    _setUpActor(USER2);
        Target.step();
        _delay(0x8fae9, 0x1740);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb10, 0x5d4d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eaaf, 0x107f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb40, 0x1388);
    _setUpActor(USER5);
        Target.step();
        _delay(0xdb, 0x71);
    _setUpActor(USER3);
        Target.step();
        _delay(0xb9, 0xc6);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2f, 0xbe);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb25, 0xb6);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb2a, 0x20);
    _setUpActor(USER2);
        Target.step();
        _delay(0x95, 0x12c2);
    _setUpActor(USER1);
        Target.step();
        _delay(0x329b9, 0x1313);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8a317, 0x1cbb);
    _setUpActor(USER4);
        Target.step();
        _delay(0x9e, 0x12e9);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8a317, 0x9);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb09, 0xbc);
    _setUpActor(USER5);
        Target.step();
        _delay(0x8d, 0x47fd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1c18d, 0xb2);
    _setUpActor(USER5);
        Target.step();
        _delay(0x98, 0xe2);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eac6, 0x1363);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2f, 0x3a9d);
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
