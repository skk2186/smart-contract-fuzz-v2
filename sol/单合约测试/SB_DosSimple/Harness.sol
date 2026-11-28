pragma solidity ^0.4.25;
import "./dos_simple.sol";

contract SBDosSimpleHarness is DosOneFunc {
    bool public resetTriggered;

    function fillStep() public {
        bool ok = ifillArray();
        if (!ok) {
            resetTriggered = true;
        }
    }

    function currentLength() public view returns (uint256) {
        return listAddresses.length;
    }

    function echidna_list_never_reset_after_1500() public view returns (bool) {
        return !resetTriggered;
    }
}
