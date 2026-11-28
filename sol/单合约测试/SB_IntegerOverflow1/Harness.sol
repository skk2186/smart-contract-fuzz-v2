pragma solidity ^0.4.24;
import "./integer_overflow_1.sol";

contract SBIntOverflow1Harness is Overflow {
    uint256 public lastAdded;
    bool public wrapped;

    function addTracked(uint256 value) public {
        require(value > 0);
        uint256 prev = lastAdded;
        add(value);
        uint256 cur;
        assembly { cur := sload(0) }
        if (cur < prev || cur < value) {
            wrapped = true;
        }
        lastAdded = cur;
    }

    function echidna_seller_balance_monotonic() public view returns (bool) {
        return !wrapped;
    }
}
