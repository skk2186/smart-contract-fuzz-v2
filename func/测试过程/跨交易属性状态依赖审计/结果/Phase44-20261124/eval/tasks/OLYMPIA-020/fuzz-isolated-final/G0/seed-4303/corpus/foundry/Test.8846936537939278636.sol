// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x30000);
    address constant USER3 = address(0x10000);
    address constant USER4 = address(0x50000);
    address constant USER5 = address(0x20000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x4eb44, 0x3c07);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6c82f, 0x58ab);
    _setUpActor(USER2);
        Target.step();
        _setUpActor(USER1);
        Target.step();
        _delay(0x4eb2d, 0x2422);
    _setUpActor(USER2);
        Target.step();
        _delay(0x37272, 0x7d93);
    _setUpActor(USER1);
        Target.step();
        _delay(0x65410, 0x4ddd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x5bd20, 0x139f);
    _setUpActor(USER2);
        Target.step();
        _delay(0xc247, 0x5daa);
    _setUpActor(USER3);
        Target.step();
        _delay(0x10978, 0x138c);
    _setUpActor(USER3);
        Target.step();
        _delay(0xb, 0x552);
    _setUpActor(USER3);
        Target.step();
        _delay(0x41a2, 0x7840);
    _setUpActor(USER4);
        Target.step();
        _delay(0x7f7c2, 0x5b6b);
    _setUpActor(USER4);
        Target.step();
        _delay(0x6123, 0x5c65);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4, 0x4);
    _setUpActor(USER5);
        Target.step();
        _delay(0x51251, 0x440);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb2d, 0x755a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6a2ce, 0x9cf);
    _setUpActor(USER5);
        Target.step();
        _delay(0x52be8, 0xe59f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb37, 0x13);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eac7, 0xc);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4eb3a, 0x47fd);
    _setUpActor(USER2);
        Target.step();
        _delay(0x4eb36, 0x58ab);
    _setUpActor(USER3);
        Target.step();
        _delay(0x8345, 0xea4f);
    _setUpActor(USER1);
        Target.step();
        _delay(0x214c9, 0x597d);
    _setUpActor(USER2);
        Target.step();
        _delay(0x433c2, 0x7fff);
    _setUpActor(USER5);
        Target.step();
        _delay(0x875e1, 0x1396);
    _setUpActor(USER4);
        Target.step();
        _delay(0x8a317, 0x1a41);
    _setUpActor(USER5);
        Target.step();
        _setUpActor(USER3);
        Target.step();
        _delay(0x4a55, 0x107f);
    _setUpActor(USER4);
        Target.step();
        _delay(0x2fa33, 0xd065);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb40, 0x1320);
    _setUpActor(USER1);
        Target.step();
        _delay(0x5c52e, 0x855a);
    _setUpActor(USER2);
        Target.step();
        _delay(0x6, 0xb0cd);
    _setUpActor(USER5);
        Target.step();
        _delay(0x4eb32, 0x9d0);
    _setUpActor(USER1);
        Target.step();
        _delay(0x8af1a, 0xa475);
    _setUpActor(USER3);
        Target.step();
        _delay(0xffff, 0x7660);
    _setUpActor(USER3);
        Target.step();
        _delay(0x1b, 0x87a0);
    _setUpActor(USER3);
        Target.step();
        _delay(0x52be8, 0x1395);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6123, 0x185a);
    _setUpActor(USER4);
        Target.step();
        _delay(0x5f467, 0x4f13);
    _setUpActor(USER4);
        Target.step();
        _delay(0x5, 0x138e);
    _setUpActor(USER2);
        Target.step();
        _delay(0x16, 0x13be);
    _setUpActor(USER4);
        Target.step();
        _delay(0xb056, 0x9a0e);
    _setUpActor(USER1);
        Target.step();
        _delay(0x7eea7, 0x6b0c);
    _setUpActor(USER4);
        Target.step();
        _delay(0x43af0, 0x185a);
    _setUpActor(USER1);
        Target.step();
        _delay(0x8a317, 0xe289);
    _setUpActor(USER1);
        Target.step();
        _delay(0x6d464, 0x89b0);
    _setUpActor(USER5);
        Target.step();
        _delay(0x7f7c2, 0x9cf);
    _setUpActor(USER4);
        Target.step();
        _delay(0x45d48, 0x1398);
    _setUpActor(USER2);
        Target.step();
        _delay(0x433c2, 0x12);
    _setUpActor(USER2);
        Target.step();
        _delay(0x7f7c2, 0x8d7);
    _setUpActor(USER1);
        Target.step();
        _delay(0x17, 0x9c1);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4eb35, 0x3032);
    _setUpActor(USER5);
        Target.step();
        _delay(0x8af1a, 0x10);
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
