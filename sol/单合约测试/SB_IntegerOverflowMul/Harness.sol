pragma solidity ^0.4.24;
import "./integer_overflow_mul.sol";

contract SBIntOverflowMulHarness is IntegerOverflowMul {
    bool public overflowedToZero;

    function runNonZero(uint256 input) public {
        require(input > 0);
        uint256 beforeVal = count;
        run(input);
        if (beforeVal > 0 && count == 0) {
            overflowedToZero = true;
        }
    }

    function echidna_count_never_wraps_to_zero() public view returns (bool) {
        return !overflowedToZero;
    }
}
