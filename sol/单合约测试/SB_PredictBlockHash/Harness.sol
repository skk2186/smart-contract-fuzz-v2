pragma solidity ^0.4.24;
import "./old_blockhash.sol";

contract SBPredictBlockHashHarness {
    PredictTheBlockHashChallenge public target;
    bool public prizeWon;

    function initChallenge() public payable {
        require(address(target) == address(0) && msg.value == 1 ether);
        target = (new PredictTheBlockHashChallenge).value(1 ether)();
    }

    function lockGuess(bytes32 hash) public payable {
        require(address(target) != address(0) && msg.value == 1 ether);
        target.lockInGuess.value(1 ether)(hash);
    }

    function settleGuess() public {
        require(address(target) != address(0));
        uint256 beforeBal = address(target).balance;
        target.settle();
        if (beforeBal >= 2 ether && address(target).balance == 0) {
            prizeWon = true;
        }
    }

    function() public payable {}

    function echidna_house_keeps_prize() public view returns (bool) {
        return !prizeWon;
    }
}
