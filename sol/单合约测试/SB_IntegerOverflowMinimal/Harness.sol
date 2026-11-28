pragma solidity ^0.4.24;
import "./integer_overflow_minimal.sol";

contract SBIntOverflowMinimalHarness is IntegerOverflowMinimal {
    function echidna_count_bounded() public view returns (bool) {
        return count <= 1;
    }
}
