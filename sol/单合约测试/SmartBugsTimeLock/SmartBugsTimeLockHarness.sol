pragma solidity 0.4.25;

/**
 * Upstream source: SmartBugs Curated (dataset/arithmetic/timelock.sol)
 * Repository: https://github.com/smartbugs/smartbugs-curated
 * License: MIT
 *
 * increaseLockTime() adds _secondsToIncrease to lockTime[msg.sender] without SafeMath,
 * enabling overflow wrap-around to bypass the 1-week withdrawal lock immediately after deposit.
 */
contract SmartBugsTimeLockHarness {
    mapping(address => uint256) public balances;
    mapping(address => uint256) public lockTime;
    mapping(address => uint256) public initialUnlockTime;
    bool public earlyWithdrawalObserved;

    event Deposited(address indexed user, uint256 amount, uint256 unlockAt);
    event LockIncreased(address indexed user, uint256 newUnlockAt);
    event Withdrawn(address indexed user, uint256 amount);

    function deposit() public payable {
        require(msg.value > 0);
        balances[msg.sender] += msg.value;
        lockTime[msg.sender] = now + 1 weeks;
        if (initialUnlockTime[msg.sender] == 0 || now + 1 weeks > initialUnlockTime[msg.sender]) {
            initialUnlockTime[msg.sender] = now + 1 weeks;
        }
        emit Deposited(msg.sender, msg.value, lockTime[msg.sender]);
    }

    function increaseLockTime(uint256 _secondsToIncrease) public {
        lockTime[msg.sender] += _secondsToIncrease;
        emit LockIncreased(msg.sender, lockTime[msg.sender]);
    }

    function withdraw() public {
        require(balances[msg.sender] > 0);
        require(now > lockTime[msg.sender]);
        if (now <= initialUnlockTime[msg.sender]) {
            earlyWithdrawalObserved = true;
        }
        uint256 transferValue = balances[msg.sender];
        balances[msg.sender] = 0;
        msg.sender.transfer(transferValue);
        emit Withdrawn(msg.sender, transferValue);
    }

    function currentTimestamp() public view returns (uint256) {
        return now;
    }

    function userLockTime(address user) public view returns (uint256) {
        return lockTime[user];
    }

    /// @notice Funds locked for 1 week must never be withdrawn before the original unlock timestamp.
    function echidna_no_early_withdrawal() public view returns (bool) {
        return !earlyWithdrawalObserved;
    }
}
