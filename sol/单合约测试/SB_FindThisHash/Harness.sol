pragma solidity ^0.4.24;
import "./FindThisHash.sol";

contract SBFindThisHashHarness is FindThisHash {
    bool public solved;

    function solvePuzzle(string solution) public {
        require(hash == keccak256(abi.encodePacked(solution)));
        solved = true;
    }

    function echidna_hash_puzzle_unsolved() public view returns (bool) {
        return !solved;
    }
}
