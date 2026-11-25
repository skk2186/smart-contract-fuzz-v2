// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x20000);
    address constant USER5 = address(0x50000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x65, 0x1344);
    _setUpActor(USER1);
        Target.step();
        _delay(0x212f1, 0xeb58);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2a, 0x2);
    _setUpActor(USER1);
        Target.step();
        _delay(0xa, 0x137b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x52be8, 0x5f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x57, 0x16);
    _setUpActor(USER5);
        Target.step();
        _delay(0xd908, 0x4f13);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4a0f1, 0x26);
    _setUpActor(USER1);
        Target.step();
        _delay(0x43af0, 0x320);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4164c, 0x22);
    _setUpActor(USER3);
        Target.step();
        _delay(0x189e3, 0x136f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x767a0, 0x1388);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3c, 0x1355);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eae1, 0x36);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eaf6, 0x134e);
    _setUpActor(USER4);
        Target.step();
        _delay(0x3cda6, 0x134d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x48, 0x610);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb34, 0x1358);
    _setUpActor(USER3);
        Target.step();
        _delay(0x47, 0x9);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1, 0x2519);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1b, 0x1344);
    _setUpActor(USER4);
        Target.step();
        _delay(0x9, 0x4d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4c, 0x66);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1b, 0x9c1);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb33, 0x5aeb);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8c149, 0xd065);
    _setUpActor(USER4);
        Target.step();
        _delay(0x15, 0x5aeb);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3e, 0x9a7b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3bf40, 0xb);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb0f, 0x1363);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb31, 0xe3d6);
    _setUpActor(USER3);
        Target.step();
        _delay(0x38, 0x1a41);
    _setUpActor(USER5);
        Target.step();
        _delay(0x668ee, 0x494f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1c5dc, 0x95ce);
    _setUpActor(USER3);
        Target.step();
        _delay(0x5f467, 0xb7e3);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eae1, 0x552);
    _setUpActor(USER3);
        Target.step();
        _delay(0x142ef, 0x6291);
    _setUpActor(USER1);
        Target.step();
        _delay(0x21, 0x3ed9);
    _setUpActor(USER4);
        Target.step();
        _delay(0x712e4, 0x1347);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb16, 0x58);
    _setUpActor(USER4);
        Target.step();
        _delay(0x15, 0x3f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x329b9, 0x1372);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eae5, 0x136c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2652e, 0x139d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eafb, 0x5b6b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x103ef, 0x1363);
    _setUpActor(USER1);
        Target.step();
        _delay(0xd, 0x65);
    _setUpActor(USER4);
        Target.step();
        _delay(0x5, 0x1350);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb41, 0x46);
    _setUpActor(USER2);
        Target.step();
        _delay(0x46b47, 0x1380);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb37, 0x1a41);
    _setUpActor(USER5);
        Target.step();
        _delay(0x1051, 0x56);
    _setUpActor(USER3);
        Target.step();
        _delay(0x712e4, 0x1356);
    _setUpActor(USER1);
        Target.step();
        _delay(0x37, 0x1cfb);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb00, 0x137f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x66815, 0x9b97);
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
