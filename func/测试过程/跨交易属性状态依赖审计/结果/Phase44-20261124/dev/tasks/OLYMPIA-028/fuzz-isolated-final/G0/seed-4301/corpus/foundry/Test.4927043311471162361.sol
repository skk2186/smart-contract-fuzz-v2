// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x50000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x20000);
    address constant USER4 = address(0x30000);
    address constant USER5 = address(0x10000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eb42, 0x7a00);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5f, 0x3032);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb21, 0x136f);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1c, 0xea96);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb28, 0xea4d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eaf1, 0x1379);
    _setUpActor(USER4);
        Target.step();
        _delay(0x35, 0x7630);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb18, 0x38a9);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb21, 0xeb6b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x9, 0x138b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8a317, 0x31);
    _setUpActor(USER2);
        Target.step();
        _delay(0x13, 0x139b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7f467, 0x1365);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4694f, 0x27);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb02, 0x7);
    _setUpActor(USER5);
        Target.step();
        _delay(0x2b, 0x1f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x28928, 0xe4d);
    _setUpActor(USER1);
        Target.step();
        _delay(0x52, 0x1351);
    _setUpActor(USER1);
        Target.step();
        _delay(0x21, 0x55);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb27, 0x5ef7);
    _setUpActor(USER2);
        Target.step();
        _delay(0x45, 0x45d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x52be8, 0x597d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb2f, 0xd619);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb3c, 0x2ae4);
    _setUpActor(USER4);
        Target.step();
        _delay(0x64ad5, 0x133c);
    _setUpActor(USER1);
        Target.step();
        _delay(0x29, 0x89b0);
    _setUpActor(USER4);
        Target.step();
        _delay(0x23, 0xd0d1);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6d464, 0x2f);
    _setUpActor(USER5);
        Target.step();
        _delay(0x75d98, 0xd0cb);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb1b, 0x5c65);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb20, 0x43);
    _setUpActor(USER3);
        Target.step();
        _delay(0x3a, 0xe5ea);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1f, 0x4);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4daf5, 0x2947);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1c5dc, 0x4a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x34, 0x2c55);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eaf9, 0x35);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb3f, 0xff);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb0d, 0x5d);
    _setUpActor(USER5);
        Target.step();
        _delay(0x53, 0x34);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb0a, 0x440);
    _setUpActor(USER2);
        Target.step();
        _delay(0x65410, 0x2e);
    _setUpActor(USER3);
        Target.step();
        _delay(0x39, 0x7f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7, 0x5caa);
    _setUpActor(USER2);
        Target.step();
        _delay(0x22, 0x1364);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb29, 0x1362);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1a, 0x5b6b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x3e, 0x133c);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5caa0, 0x47fd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x62123, 0x4a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x24, 0x37);
    _setUpActor(USER5);
        Target.step();
        _delay(0x475d0, 0x1342);
    _setUpActor(USER2);
        Target.step();
        _delay(0x17, 0x10);
    _setUpActor(USER4);
        Target.step();
        _delay(0xc247, 0x1349);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb32, 0x2f7b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2, 0x3a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb29, 0x5d);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eae9, 0xd0e9);
    _setUpActor(USER2);
        Target.step();
        _setUpActor(USER2);
        Target.step();
        _delay(0x44058, 0x7c0);
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
