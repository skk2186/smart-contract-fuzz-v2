pragma solidity ^0.4.24;
import "./FibonacciBalance.sol";

contract SBFibonacciHarness {
    FibonacciLib public lib;
    FibonacciBalance public target;
    bool public drained;

    function init() public payable {
        require(address(target) == address(0) && msg.value >= 2 ether);
        lib = new FibonacciLib();
        target = (new FibonacciBalance).value(msg.value)(address(lib));
    }

    function callWithdraw() public {
        require(address(target) != address(0));
        uint256 b = address(target).balance;
        target.withdraw();
        if (address(target).balance < b) {
            drained = true;
        }
    }

    function() public payable {}

    function echidna_lib_start_not_hijacked() public view returns (bool) {
        return !drained;
    }
}
