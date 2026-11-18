// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x20000);
    address constant USER2 = address(0x10000);
    address constant USER3 = address(0x40000);
    address constant USER4 = address(0x30000);

    // TODO: Replace with your actual contract instance
    CryticTester Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new CryticTester();
  }

  function test_replay() public {
        _delay(0x875e, 0xb7ba);
    _setUpActor(USER1);
        Target.testNonRebasingSupplyVsTotalSupply();
        _delay(0x14580, 0xcd5f);
    _setUpActor(USER2);
        Target.testTransferBalanceSentMore(255, 116, 0);
        _delay(0x6674, 0x13990);
    _setUpActor(USER1);
        Target.getTotalBalance();
        _delay(0xa36d, 0x7a4c);
    _setUpActor(USER3);
        Target.testTotalNonRebasingSupplyLessThanTotalBalance();
        _delay(0x388c, 0xf3e9);
    _setUpActor(USER2);
        Target.testOptInBalanceRounding(145);
        _delay(0x1df4, 0x112f2);
    _setUpActor(USER4);
        Target.testChangeSupply(111285967965049253373569944471175151238352688946811268998405366345023863368939);
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
