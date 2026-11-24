// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x10000);
    address constant USER3 = address(0x30000);

    // TODO: Replace with your actual contract instance
    CryticTester Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new CryticTester();
  }

  function test_replay() public {
        _delay(0x32a8, 0x739a);
    _setUpActor(USER1);
        Target.governance_claimForInitiative(104);
        _delay(0x39, 0x4473);
    _setUpActor(USER2);
        Target.invariant_GV01();
        _delay(0x1b0ec, 0x168);
    _setUpActor(USER3);
        Target.governance_depositLQTY(189380465702600551405901893);
        _delay(0x36c16, 0x7f);
    _setUpActor(USER2);
        Target.helper_deployInitiative();
        _delay(0x901c6, 0x2a);
    _setUpActor(USER1);
        Target.invariant_BI05();
        _delay(0x37626, 0x44c2);
    _setUpActor(USER2);
        Target.invariant_GV01();
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
