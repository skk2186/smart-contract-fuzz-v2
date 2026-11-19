pragma solidity ^0.4.24;

import "./Wallet.sol";

contract WalletHarness {
    Wallet private wallet;
    uint256 public cumulativeDeposits;
    uint256 public cumulativePayout;

    constructor() public {
        wallet = new Wallet();
    }

    function deposit() public payable {
        wallet.deposit.value(msg.value)();
        cumulativeDeposits += msg.value;
    }

    function withdraw(uint256 amount) public {
        uint256 balanceBefore = address(this).balance;
        wallet.withdraw(amount);
        cumulativePayout += address(this).balance - balanceBefore;
    }

    function refund() public {
        uint256 balanceBefore = address(this).balance;
        wallet.refund();
        cumulativePayout += address(this).balance - balanceBefore;
    }

    function echidna_wallet_accounting_respected() public view returns (bool) {
        return cumulativePayout <= cumulativeDeposits;
    }

    function() public payable {}
}
