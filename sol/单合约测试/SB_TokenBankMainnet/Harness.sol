pragma solidity ^0.4.24;
import "./0x39cfd754c85023648bf003bea2dd498c5612abfa.sol";

contract SBTokenBankHarness is TokenBank {
    address public initialOwner;

    constructor() public {
        initTokenBank();
        initialOwner = msg.sender;
    }

    function currentOwner() public view returns (address) {
        return owner;
    }

    function echidna_owner_preserved() public view returns (bool) {
        return owner == initialOwner;
    }
}
