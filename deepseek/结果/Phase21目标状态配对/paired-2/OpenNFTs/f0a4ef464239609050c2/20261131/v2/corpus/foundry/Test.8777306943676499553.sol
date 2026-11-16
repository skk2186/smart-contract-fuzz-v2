// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x2a);

    // TODO: Replace with your actual contract instance
    OpenAutoMarketExFuzz Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new OpenAutoMarketExFuzz();
  }

  function test_replay() public {
        _setUpActor(USER1);
        Target.transferOwnership(address(0x65536));
        vm.stopPrank();
        vm.prank(address(0x10000));
        assertFalse(Target.echidna_owner());
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
