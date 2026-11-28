pragma solidity ^0.4.25;
import "./dos_address.sol";

contract SBDosAddressHarness is DosGas {
    function echidna_not_won_via_unbounded_loop() public view returns (bool) {
        return !iWin();
    }
}
