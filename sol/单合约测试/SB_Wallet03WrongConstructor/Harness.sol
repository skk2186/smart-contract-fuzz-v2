pragma solidity ^0.4.24;
import "./wallet_03_wrong_constructor.sol";

contract SBWallet03Harness is Wallet {
    address public initialDeployer;
    uint256 public totalDeposited;
    bool public unauthorizedDrain;

    constructor() public {
        initialDeployer = msg.sender;
        creator = msg.sender;
    }

    function depositFunds() public payable {
        require(msg.value > 0);
        totalDeposited += msg.value;
        deposit();
    }

    function migrateFunds(address to) public {
        uint256 beforeBal = address(this).balance;
        migrateTo(to);
        if (beforeBal > 0 && msg.sender != initialDeployer) {
            unauthorizedDrain = true;
        }
    }

    function echidna_only_deployer_keeps_funds() public view returns (bool) {
        return !unauthorizedDrain;
    }
}
