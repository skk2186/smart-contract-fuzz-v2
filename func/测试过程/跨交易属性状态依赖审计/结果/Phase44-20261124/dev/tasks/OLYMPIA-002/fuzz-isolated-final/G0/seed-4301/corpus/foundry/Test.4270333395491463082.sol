// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x20000);
    address constant USER3 = address(0x50000);
    address constant USER4 = address(0x40000);
    address constant USER5 = address(0x30000);

    // TODO: Replace with your actual contract instance
    Maze Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Maze();
  }

  function test_replay() public {
        _delay(0x2, 0x20ff);
    _setUpActor(USER1);
        Target.step();
        _delay(0x65373, 0x1394);
    _setUpActor(USER2);
        Target.step();
        _delay(0x63720, 0x5b6b);
    _setUpActor(USER3);
        Target.step();
        _delay(0x4694f, 0xb0ba);
    _setUpActor(USER4);
        Target.step();
        _delay(0x4a55, 0x139b);
    _setUpActor(USER4);
        Target.step();
        _delay(0xc06e, 0x3c09);
    _setUpActor(USER4);
        Target.step();
        _delay(0x1b, 0x1740);
    _setUpActor(USER5);
        Target.step();
        _delay(0x142ef, 0x4093);
    _setUpActor(USER1);
        Target.step();
        _delay(0x8af1a, 0x6b0c);
    _setUpActor(USER2);
        Target.step();
        _delay(0x60ceb, 0xd619);
    _setUpActor(USER5);
        Target.step();
        _delay(0x3340a, 0xc2f);
    _setUpActor(USER3);
        Target.step();
        _delay(0x7eea7, 0xcfae);
    _setUpActor(USER5);
        Target.step();
        _delay(0xb, 0x4ddd);
    _setUpActor(USER5);
        Target.step();
        _delay(0x14, 0x5d4d);
    _setUpActor(USER3);
        Target.step();
        _delay(0x76ea6, 0x138f);
    _setUpActor(USER2);
        Target.step();
        _delay(0x74d9f, 0x2f7b);
    _setUpActor(USER5);
        Target.step();
        _delay(0x64ad5, 0x47fd);
    _setUpActor(USER1);
        Target.step();
        _delay(0x4eb2c, 0xe59f);
    _setUpActor(USER2);
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
