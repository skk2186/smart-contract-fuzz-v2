pragma solidity ^0.4.24;
import "./overflow_single_tx.sol";

contract SBOverflowSingleTxHarness is IntegerOverflowSingleTransaction {
    function echidna_count_stays_nonzero_bounded() public view returns (bool) {
        return count > 0 && count < (1 << 200);
    }
}
