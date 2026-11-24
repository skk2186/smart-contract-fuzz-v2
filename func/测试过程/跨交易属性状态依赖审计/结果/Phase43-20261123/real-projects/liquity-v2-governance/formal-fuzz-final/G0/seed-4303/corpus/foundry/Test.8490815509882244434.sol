// SPDX-License-Identifier: Unlicense
pragma solidity ^0.8.0;

import "forge-std/Test.sol";

contract FoundryTest is Test {
    address constant USER1 = address(0x40000);
    address constant USER2 = address(0x10000);
    address constant USER3 = address(0x30000);

    // TODO: Replace with your actual contract instance
    CryticTester Target;

  function setUp() public {
      // TODO: Initialize your contract here
      Target = new CryticTester();
  }

  function test_replay() public {
        _delay(0xb, 0x653d);
    _setUpActor(USER1);
        Target.governance_depositLQTY(12);
        _delay(0x57c9e, 0x755b);
    _setUpActor(USER2);
        Target.invariant_BI03();
        _delay(0x94ab, 0x9730);
    _setUpActor(USER2);
        Target.invariant_GV01();
        _delay(0x4eaee, 0x9a2c);
    _setUpActor(USER3);
        Target.governance_allocateLQTY_clamped_single_initiative(252, 70318810557275334694488682764, 4099);
        _delay(0x4eb3b, 0x8a87);
    _setUpActor(USER1);
        Target.assert_canary_ASSERTION_CANARY(60464220412809727589489513206377328157259958072390521026644532965681189251166);
        _delay(0x11d53, 0x7ffc);
    _setUpActor(USER2);
        Target.invariant_BI04();
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
