// SPDX-License-Identifier: GPL-3.0-or-later
pragma solidity >=0.4.23 <0.6;

import "./DSToken原始合约.sol";

// V2 analysis fixture: these properties were added for static-analysis
// feasibility checks. They are not part of the upstream DSToken source.
contract DSTokenPropertyHarness is DSToken {
    constructor() public DSToken("DST") {}

    function echidna_actor_balance_within_supply() public view returns (bool) {
        return balanceOf[address(0x10000)] <= totalSupply;
    }

    // Diagnostic property; this token allows a transfer to address(0).
    function echidna_zero_address_empty() public view returns (bool) {
        return balanceOf[address(0)] == 0;
    }
}
