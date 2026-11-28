pragma solidity ^0.4.24;
import "./multiowned_vulnerable.sol";

contract SBMultiOwnableHarness is TestContract {
    bool public nonRootDrained;

    function fundVault() public payable {
        require(msg.value > 0);
    }

    function guardedWithdrawAll() public {
        uint256 beforeBal = address(this).balance;
        withdrawAll();
        if (beforeBal > 0 && msg.sender != root) {
            nonRootDrained = true;
        }
    }

    function echidna_non_root_cannot_drain() public view returns (bool) {
        return !nonRootDrained;
    }
}
