// SPDX-License-Identifier: GPL-3.0-or-later
pragma solidity >=0.4.22 <0.6;

import "./WETH9原始合约.sol";

// V2 analysis fixture: these properties were added for static-analysis
// feasibility checks. They are not part of the upstream WETH9 source.
contract WETH9PropertyHarness is WETH9 {
    function echidna_actor_balance_within_supply() public view returns (bool) {
        return balanceOf[address(0x10000)] <= totalSupply();
    }

    // Diagnostic property; WETH9 permits transfers to address(0), so this
    // property is expected to be falsifiable. It is not an upstream promise.
    function echidna_zero_address_empty() public view returns (bool) {
        return balanceOf[address(0)] == 0;
    }
}
