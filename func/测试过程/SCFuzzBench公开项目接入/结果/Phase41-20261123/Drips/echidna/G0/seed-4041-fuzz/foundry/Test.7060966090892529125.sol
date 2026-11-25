// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x20000);
    address constant USER3 = address(0x40000);

    // TODO: Replace with your actual contract instance
    Echidna Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new Echidna();
  }

  function test_replay() public {
        _delay(0x4e, 0x62c);
    _setUpActor(USER1);
        Target.receiveStreamsAllCycles(130);
        _delay(0x13393, 0xc2f7);
    _setUpActor(USER2);
        Target.invariantWithdrawAllTokens();
        _delay(0x13fd0, 0x41f5);
    _setUpActor(USER1);
        Target.addStreamWithClamping(158, 70, 1524785991, 1820079882, 0, 1524785992);
        _delay(0xd83d, 0x4026);
    _setUpActor(USER3);
        Target.setStreamsWithClamping(94, 165, 802619141138328374465588998858164978205024497716, 0, 1524785991, 170141183460469231731687303715884105727);
        _delay(0x4b3c, 0x3f32);
    _setUpActor(USER2);
        Target.invariantWithdrawAllTokensShouldNotRevert();
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
