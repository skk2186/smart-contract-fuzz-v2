pragma solidity ^0.4.24;
import "./unprotected0.sol";

contract SBUnprotectedHarness is Unprotected {
    address public initialOwner;
    bool public nonInitialTriggered;

    constructor() public {
        initialOwner = msg.sender;
    }

    function privilegedAction() public onlyowner {
        if (msg.sender != initialOwner) {
            nonInitialTriggered = true;
        }
    }

    function echidna_only_initial_owner_privileged() public view returns (bool) {
        return !nonInitialTriggered;
    }
}
