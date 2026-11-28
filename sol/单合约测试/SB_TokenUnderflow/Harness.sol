pragma solidity ^0.4.24;
import "./token.sol";

contract SBTokenUnderflowHarness is Token {
    address public constant USER1 = 0x0000000000000000000000000000000000010000;
    address public constant USER2 = 0x0000000000000000000000000000000000020000;

    constructor() Token(1000) public {
        balances[USER1] = 20;
    }

    function echidna_balances_bounded_by_supply() public view returns (bool) {
        return balances[USER1] <= totalSupply && balances[USER2] <= totalSupply;
    }
}
