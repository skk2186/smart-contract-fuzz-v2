// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x10000);
    address constant USER2 = address(0x20000);
    address constant USER3 = address(0x40000);

    // TODO: Replace with your actual contract instance
    CryticTester Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new CryticTester();
  }

  function test_replay() public {
        _delay(0x106a2, 0xd23f);
    _setUpActor(USER2);
        Target.testMintBalanceRounding(250, 106685643741489427940131500084259217102073690804613555045863796580802562296311);
        _delay(0x1410e, 0xf3e9);
    _setUpActor(USER2);
        Target.changeSupply(80855532112713551346504000918388687557792328239451384678541302836988733730947);
        _delay(0x1df4, 0xcb85);
    _setUpActor(USER3);
        Target.testOptInBalance(231);
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
