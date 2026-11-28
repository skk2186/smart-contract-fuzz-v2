pragma solidity ^0.4.24;
import "./ERC20.sol";

contract SBERC20FrontRunHarness is ERC20 {
    address public constant OWNER = 0x0000000000000000000000000000000000010000;
    address public constant SPENDER = 0x0000000000000000000000000000000000020000;
    uint256 public highestSingleApproval;
    uint256 public totalSpentBySpender;
    bool public capExceededAfterReset;

    constructor() ERC20(1000) public {
        transfer(OWNER, 1000);
    }

    function ownerApprove(address spender, uint256 value) public {
        require(msg.sender == OWNER && spender == SPENDER && value > 0 && value <= 100);
        if (value > highestSingleApproval) {
            highestSingleApproval = value;
        }
        approve(spender, value);
    }

    function spenderPull(address to, uint256 value) public {
        require(msg.sender == SPENDER && value > 0);
        transferFrom(OWNER, to, value);
        totalSpentBySpender += value;
        if (highestSingleApproval > 0 && totalSpentBySpender > highestSingleApproval) {
            capExceededAfterReset = true;
        }
    }

    function echidna_spender_respects_reduced_cap() public view returns (bool) {
        return !capExceededAfterReset;
    }
}
