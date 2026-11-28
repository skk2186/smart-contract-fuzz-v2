pragma solidity ^0.4.24;
import "./mapping_write.sol";

contract SBMappingWriteHarness is Map {
    address public initialOwner;

    constructor() public {
        owner = msg.sender;
        initialOwner = msg.sender;
    }

    function echidna_owner_unchanged() public view returns (bool) {
        return owner == initialOwner;
    }
}
