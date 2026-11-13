// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.20;

// Adapted from Figure 2(a) of Grieco et al., ISSTA 2020.
// The two setters omit unused bool return values and the property is view.
contract TEST {
    bool public flag0;
    bool public flag1;

    function set0(int256 val) public {
        if (val % 100 == 23) {
            flag0 = true;
        }
    }

    function set1(int256 val) public {
        if (val % 10 == 5 && flag0) {
            flag1 = true;
        }
    }

    function echidna_flag() public view returns (bool) {
        return !flag1;
    }
}
