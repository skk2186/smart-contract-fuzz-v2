// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x30000);
    address constant USER5 = address(0x50000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x46b47, 0x1375);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3d, 0x1a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3a, 0x23);
    _setUpActor(USER3);
        Target.step();
        _delay(0x29, 0x1b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x5e, 0x137e);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb02, 0xb7ea);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6b721, 0x12);
    _setUpActor(USER2);
        Target.step();
        _delay(0x25ee1, 0x20);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6123, 0x1);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2f1b5, 0x7f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6a2ce, 0xcf13);
    _setUpActor(USER5);
        Target.step();
        _delay(0x15, 0x134d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4d, 0x1367);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb37, 0x66);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4daf5, 0x1394);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb1b, 0x1379);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb28, 0x137f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb32, 0x1c);
    _setUpActor(USER3);
        Target.step();
        _delay(0x40, 0x14);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7f7c2, 0x463);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1c18d, 0x24);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3c946, 0x1475);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4a55, 0x3032);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaea, 0x1367);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eaf0, 0x8980);
    _setUpActor(USER4);
        Target.step();
        _delay(0x13, 0x7840);
    _setUpActor(USER2);
        Target.step();
        _delay(0x85b27, 0x94d4);
    _setUpActor(USER1);
        Target.step();
        _setUpActor(USER4);
        Target.step();
        _delay(0x4eaf3, 0x59);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6b721, 0x597d);
    _setUpActor(USER1);
        Target.step();
        _setUpActor(USER4);
        Target.step();
        _delay(0x4eb30, 0x1363);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb3d, 0xcad0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3c, 0x9bc);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb46, 0x23);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb1d, 0x1475);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb02, 0x26ee);
    _setUpActor(USER1);
        Target.step();
        _delay(0x51251, 0xe);
    _setUpActor(USER4);
        Target.step();
        _delay(0x52, 0xea4e);
    _setUpActor(USER1);
        Target.step();
        _delay(0x45, 0x4e);
    _setUpActor(USER3);
        Target.step();
        _delay(0x580b0, 0x138b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6c82f, 0x134c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x5f467, 0x1fd3);
    _setUpActor(USER4);
        Target.step();
        _delay(0x22, 0x54);
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
