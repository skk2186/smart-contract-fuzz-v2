pragma solidity ^0.4.24;
import "./rubixi.sol";

contract SBRubixiHarness is Rubixi {
    address public initialDeployer;
    bool public unauthorizedFeeCollect;

    constructor() public {
        initialDeployer = msg.sender;
        DynamicPyramid();
    }

    function contributeFee() public payable {
        require(msg.value > 0 && msg.value < 1 ether);
        // Trigger fallback fee accumulation through self-call or direct value
        require(address(this).call.value(msg.value)());
    }

    function guardedCollectAllFees() public {
        uint256 beforeBal = address(this).balance;
        collectAllFees();
        if (beforeBal > 0 && msg.sender != initialDeployer) {
            unauthorizedFeeCollect = true;
        }
    }

    function echidna_fees_not_taken_by_non_deployer() public view returns (bool) {
        return !unauthorizedFeeCollect;
    }
}
