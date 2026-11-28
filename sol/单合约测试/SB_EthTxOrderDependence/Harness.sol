pragma solidity ^0.4.24;
import "./eth_tx_order_dependence_minimal.sol";

contract SBEthTxOrderHarness is EthTxOrderDependenceMinimal {
    bool public outsiderClaimedNonZero;

    function ownerSetReward() public payable {
        require(msg.value >= 1 ether);
        setReward();
    }

    function userClaimReward(uint256 submission) public {
        uint256 r = reward;
        claimReward(submission);
        if (r >= 1 ether && msg.sender != owner) {
            outsiderClaimedNonZero = true;
        }
    }

    function echidna_reward_not_claimed_by_outsider() public view returns (bool) {
        return !outsiderClaimedNonZero;
    }
}
