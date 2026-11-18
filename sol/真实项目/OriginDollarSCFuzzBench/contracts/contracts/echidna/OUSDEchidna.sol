// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.0;

import "../token/OUSD.sol";

contract OUSDEchidna is OUSD {
    constructor() OUSD() {
        // The Yield Delegation rewrite (#2298) left Governable without a
        // constructor, so the governor slot is zero and the harness could
        // never call initialize() (onlyGovernor). Make the deploying harness
        // the governor so the suite is runnable again.
        _setGovernor(msg.sender);
    }

    function _isNonRebasingAccountEchidna(address _account)
        public
        returns (bool)
    {
        _autoMigrate(_account);
        return alternativeCreditsPerToken[_account] > 0;
    }
}
