pragma solidity ^0.4.24;
import "./name_registrar.sol";

contract SBNameRegistrarHarness is NameRegistrar {
    function echidna_registrar_stays_locked() public view returns (bool) {
        return !unlocked;
    }
}
