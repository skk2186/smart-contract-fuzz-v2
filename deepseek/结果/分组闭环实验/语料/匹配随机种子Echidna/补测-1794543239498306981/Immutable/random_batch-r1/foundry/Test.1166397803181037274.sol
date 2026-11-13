// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {

    // TODO: Replace with your actual contract instance
    ERC721PsiV2Echidna Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new ERC721PsiV2Echidna();
  }

  function test_replay() public {
        vm.stopPrank();
        vm.prank(address(0x10000));
        assertFalse(Target.echidna_mint_boundary_check());
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
