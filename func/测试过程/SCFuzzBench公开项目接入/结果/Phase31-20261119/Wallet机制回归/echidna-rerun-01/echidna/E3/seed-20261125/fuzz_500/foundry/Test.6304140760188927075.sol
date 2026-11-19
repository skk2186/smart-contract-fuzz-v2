// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);

    // TODO: Replace with your actual contract instance
    WalletHarness Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new WalletHarness();
  }

  function test_replay() public {
        _setUpActor(USER1);
        Target.deposit(0);
        _setUpActor(USER1);
        Target.refund(0);
        _setUpActor(USER1);
        Target.deposit(1);
        _setUpActor(USER1);
        Target.withdraw(0, 330330969467021044);
        vm.stopPrank();
        vm.prank(address(0x10000));
        assertFalse(Target.echidna_wallet_accounting_respected());
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
