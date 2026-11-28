pragma solidity 0.4.25;
import "./overflow_simple_add.sol";

contract SBOverflowSimpleAddHarness is Overflow_Add {
    function echidna_balance_never_zero() public view returns (bool) {
        return balance >= 1;
    }
}
