// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.0;

import {Echidna} from "../../contracts/contracts/echidna/Echidna.sol";

/// @notice scfuzzbench adaptation layer: canary checks on top of the
/// upstream OUSD Echidna suite. Assertion failures are surfaced the same
/// way for Echidna, Medusa, Foundry, and Recon (AssertionFailed event +
/// assert), and dedup to the emitting function name across fuzzers.
abstract contract Properties is Echidna {
    string internal constant ASSERTION_CANARY = "!!! canary assertion";
    string internal constant INVARIANT_CANARY_GLOBAL_INVARIANT_FAILURE = "Canary invariant";

    event AssertionFailed(string reason);

    function t(bool b, string memory reason) internal {
        if (!b) {
            emit AssertionFailed(reason);
            assert(false);
        }
    }

    function invariant_canary() public returns (bool) {
        t(false, INVARIANT_CANARY_GLOBAL_INVARIANT_FAILURE);
        return true;
    }

    function assert_canary_ASSERTION_CANARY(uint256 entropy) public {
        t(entropy > 0, ASSERTION_CANARY);
    }
}
