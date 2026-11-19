pragma solidity ^0.4.24;

import "./Wallet.sol";

contract WalletUser {
    Wallet private wallet;

    constructor(Wallet target) public {
        wallet = target;
    }

    function deposit() public payable {
        wallet.deposit.value(msg.value)();
    }

    function withdraw(uint256 amount) public {
        wallet.withdraw(amount);
    }

    function refund() public {
        wallet.refund();
    }

    function() public payable {}
}

contract WalletHarness {
    uint8 private constant ACCOUNT_COUNT = 5;
    WalletUser[5] private accounts;
    mapping(uint8 => uint256) public cumulativeDeposits;
    mapping(uint8 => uint256) public cumulativePayout;

    constructor() public {
        Wallet wallet = new Wallet();
        for (uint8 i = 0; i < ACCOUNT_COUNT; i++) {
            accounts[i] = new WalletUser(wallet);
        }
    }

    function deposit(uint8 account) public payable {
        uint8 actor = account % ACCOUNT_COUNT;
        accounts[actor].deposit.value(msg.value)();
        cumulativeDeposits[actor] += msg.value;
    }

    function withdraw(uint8 account, uint256 amount) public {
        uint8 actor = account % ACCOUNT_COUNT;
        uint256 balanceBefore = address(accounts[actor]).balance;
        accounts[actor].withdraw(amount);
        cumulativePayout[actor] += address(accounts[actor]).balance - balanceBefore;
    }

    function refund(uint8 account) public {
        uint8 actor = account % ACCOUNT_COUNT;
        uint256 balanceBefore = address(accounts[actor]).balance;
        accounts[actor].refund();
        cumulativePayout[actor] += address(accounts[actor]).balance - balanceBefore;
    }

    function echidna_wallet_accounting_respected() public view returns (bool) {
        for (uint8 i = 0; i < ACCOUNT_COUNT; i++) {
            if (cumulativePayout[i] > cumulativeDeposits[i]) {
                return false;
            }
        }
        return true;
    }
}
