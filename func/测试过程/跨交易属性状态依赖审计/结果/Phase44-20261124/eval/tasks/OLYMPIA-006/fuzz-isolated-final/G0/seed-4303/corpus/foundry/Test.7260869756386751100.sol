// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x10000);
    address constant USER3 = address(0x30000);
    address constant USER4 = address(0x40000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eb1e, 0x89b0);
    _setUpActor(USER2);
        Target.step();
        _delay(0x142ee, 0x85e0);
    _setUpActor(USER1);
        Target.step();
        _setUpActor(USER2);
        Target.step();
        _delay(0x142f0, 0xd13a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x2e, 0x12);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1cae0, 0x138d);
    _setUpActor(USER1);
        Target.step();
        _setUpActor(USER2);
        Target.step();
        _delay(0x45484, 0x9ae0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x291ac, 0x1);
    _setUpActor(USER2);
        Target.step();
        _setUpActor(USER2);
        Target.step();
        _delay(0x10, 0x18);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6d464, 0x1394);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2f, 0xd1ae);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb1e, 0x2a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x11d50, 0x7fff);
    _setUpActor(USER3);
        Target.step();
        _delay(0x6b721, 0x4cc2);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5674a, 0x9);
    _setUpActor(USER2);
        Target.step();
        _setUpActor(USER1);
        Target.step();
        _delay(0x39c08, 0x2e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6b504, 0x1389);
    _setUpActor(USER1);
        Target.step();
        _setUpActor(USER1);
        Target.step();
        _delay(0x7cf4e, 0xd253);
    _setUpActor(USER3);
        Target.step();
        _delay(0x668ee, 0x94d4);
    _setUpActor(USER2);
        Target.step();
        _setUpActor(USER1);
        Target.step();
        _setUpActor(USER3);
        Target.step();
        _delay(0x24b01, 0x9cf);
    _setUpActor(USER1);
        Target.step();
        _delay(0x329b9, 0xe4d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x28928, 0x116e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x65373, 0x1374);
    _setUpActor(USER2);
        Target.step();
        _delay(0x3340a, 0x387a);
    _setUpActor(USER3);
        Target.step();
        _delay(0x329b9, 0x1372);
    _setUpActor(USER2);
        Target.step();
        _delay(0x11d50, 0x139b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x65410, 0x2b);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb30, 0x47fd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb1a, 0x7fe1);
    _setUpActor(USER2);
        Target.step();
        _delay(0x1c5dc, 0xea4d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x189e3, 0x11);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb37, 0x16);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6c82f, 0x1);
    _setUpActor(USER2);
        Target.step();
        _delay(0x62123, 0x5c65);
    _setUpActor(USER1);
        Target.step();
        _delay(0xc4b, 0x138f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x1c18d, 0x7be8);
    _setUpActor(USER3);
        Target.step();
        _setUpActor(USER2);
        Target.step();
        _setUpActor(USER1);
        Target.step();
        _delay(0x6d828, 0x13);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4e37f, 0xd8f2);
    _setUpActor(USER1);
        Target.step();
        _delay(0x2, 0x4269);
    _setUpActor(USER4);
        Target.step();
        _setUpActor(USER2);
        Target.step();
        _delay(0x769f1, 0x2e81);
    _setUpActor(USER3);
        Target.step();
        _delay(0xb056, 0x8980);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7, 0x824d);
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
