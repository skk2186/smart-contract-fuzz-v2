pragma solidity ^0.4.24;
import "./integer_overflow_multitx_multifunc_feasible.sol";

contract SBMultiTxOverflowHarness is IntegerOverflowMultiTxMultiFuncFeasible {
    function echidna_count_no_underflow() public view returns (bool) {
        return count <= 1;
    }
}
