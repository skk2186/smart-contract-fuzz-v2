pragma solidity ^0.4.24;
import "./odds_and_evens.sol";

contract SBOddsAndEvensHarness is OddsAndEvens {
    bool public roundCompleted;

    function playRound(uint256 number) public payable {
        uint8 beforeTot = tot;
        play(number);
        if (beforeTot == 1 && tot == 0) {
            roundCompleted = true;
        }
    }

    function echidna_second_player_cannot_always_win() public view returns (bool) {
        return !roundCompleted;
    }
}
