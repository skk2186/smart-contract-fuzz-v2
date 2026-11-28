pragma solidity ^0.4.25;
import "./arbitrary_location_write_simple.sol";

contract SBArbitraryWriteHarness is Wallet {
    address public expectedOwner;

    constructor() public {
        expectedOwner = msg.sender;
    }

    function currentSlot1Owner() public view returns (address o) {
        assembly { o := sload(1) }
    }

    function bonusCodesLength() public view returns (uint256 l) {
        assembly { l := sload(0) }
    }

    function echidna_owner_slot_intact() public view returns (bool) {
        return currentSlot1Owner() == expectedOwner;
    }
}
