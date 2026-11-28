pragma solidity ^0.4.24;
import "./guess_the_random_number.sol";

contract SBGuessRandomHarness {
    GuessTheRandomNumberChallenge public challenge;

    function initChallenge() public payable {
        require(address(challenge) == address(0) && msg.value == 1 ether);
        challenge = (new GuessTheRandomNumberChallenge).value(1 ether)();
    }

    function guessNumber(uint8 n) public payable {
        require(address(challenge) != address(0) && msg.value == 1 ether);
        challenge.guess.value(1 ether)(n);
    }

    function() public payable {}

    function echidna_challenge_not_completed() public view returns (bool) {
        if (address(challenge) == address(0)) {
            return true;
        }
        return !challenge.isComplete();
    }
}
