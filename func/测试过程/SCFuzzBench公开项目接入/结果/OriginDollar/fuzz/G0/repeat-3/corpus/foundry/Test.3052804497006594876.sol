// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x40000);
    address constant USER3 = address(0x20000);

    // TODO: Replace with your actual contract instance
    CryticTester Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new CryticTester();
  }

  function test_replay() public {
        _delay(0x65c2, 0xf9fa);
    _setUpActor(USER1);
        Target.getTotalBalance();
        _delay(0x123fd, 0xffff);
    _setUpActor(USER1);
        Target.testNonRebasingSupplyVsTotalSupply();
        _setUpActor(USER3);
        Target.testMintBalanceRounding(10, 95451617745871330410447221236797276881704723921478846674771081516053146594407);
        _delay(0x13fd0, 0x1332);
    _setUpActor(USER3);
        Target.testMintBalanceRounding(23, 32997391165353018583006285436907372099343295187193869927323397448897417440796);
        _delay(0xfa2b, 0xc6d9);
    _setUpActor(USER1);
        Target.testChangeSupply(78787535048680856701459037207033762637154945675369341790391589816677685451243);
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
