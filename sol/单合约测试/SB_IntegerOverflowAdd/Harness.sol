pragma solidity ^0.4.24;
import "./integer_overflow_add.sol";

contract SBIntOverflowAddHarness is IntegerOverflowAdd {
    function echidna_count_never_zero() public view returns (bool) {
        return count >= 1;
    }
}
