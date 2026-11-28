pragma solidity ^0.4.24;
import "./wallet_04_confused_sign.sol";

contract SBWallet04Harness is Wallet {
    mapping(address => uint256) public trackedDeposit;
    mapping(address => uint256) public trackedWithdraw;
    bool public overWithdrawn;

    function depositTracked() public payable {
        require(msg.value > 0);
        trackedDeposit[msg.sender] += msg.value;
        deposit();
    }

    function withdrawTracked(uint256 amount) public {
        require(amount > 0);
        withdraw(amount);
        trackedWithdraw[msg.sender] += amount;
        if (trackedWithdraw[msg.sender] > trackedDeposit[msg.sender]) {
            overWithdrawn = true;
        }
    }

    function echidna_withdraw_bounded_by_deposit() public view returns (bool) {
        return !overWithdrawn;
    }
}
