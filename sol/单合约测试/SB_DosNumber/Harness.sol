pragma solidity ^0.4.25;
import "./dos_number.sol";

contract SBDosNumberHarness is DosNumber {
    function echidna_array_below_dos_threshold() public view returns (bool) {
        return getLengthArray() <= 1500;
    }
}
