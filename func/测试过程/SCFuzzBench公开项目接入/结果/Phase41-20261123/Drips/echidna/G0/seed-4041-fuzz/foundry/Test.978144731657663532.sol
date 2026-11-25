// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x30000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x20000);

    // TODO: Replace with your actual contract instance
    Echidna Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Echidna();
  }

  function test_replay() public {
        _delay(0x10e4d, 0x34bb);
    _setUpActor(USER1);
        Target.addStreamImmediatelySqueezable(255, 49, 463586538852462923557873315974828583286719912805);
        _delay(0x10f4c, 0xfb5e);
    _setUpActor(USER2);
        Target.testSetSplitsShouldNotRevert(63, 255, 1524785993);
        _delay(0x83a9, 0x3f28);
    _setUpActor(USER1);
        Target.collectToSelf(230);
        _delay(0xb75e, 0xcce5);
    _setUpActor(USER1);
        Target.testReceiveStreams(255, 1525152930);
        _delay(0x91fe, 0x119dc);
    _setUpActor(USER1);
        Target.testReceiveStreamsShouldNotRevert(8);
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
