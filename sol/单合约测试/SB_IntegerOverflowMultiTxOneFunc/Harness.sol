pragma solidity ^0.4.24;
import "./integer_overflow_multitx_onefunc_feasible.sol";

contract SBOneFuncOverflowHarness is IntegerOverflowMultiTxOneFuncFeasible {
    function echidna_count_no_underflow() public view returns (bool) {
        return count <= 1;
    }
}
