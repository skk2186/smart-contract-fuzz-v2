pragma solidity ^0.4.24;
import "./incorrect_constructor_name1.sol";

contract SBIncorrectCtor1Harness is Missing {
    address public deployerAddr;
    bool public stolen;

    constructor() public {
        deployerAddr = msg.sender;
    }

    function fund() public payable {
        require(msg.value > 0);
    }

    function withdrawFunds() public {
        uint256 beforeBal = address(this).balance;
        withdraw();
        if (beforeBal > 0 && msg.sender != deployerAddr) {
            stolen = true;
        }
    }

    function echidna_funds_not_stolen() public view returns (bool) {
        return !stolen;
    }
}
