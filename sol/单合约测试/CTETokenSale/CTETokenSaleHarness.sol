pragma solidity 0.4.25;

/**
 * Upstream source: Capture the Ether - Token Sale Challenge
 * Reference: https://capturetheether.com/challenges/math/token-sale/
 * License: MIT
 *
 * buy(numTokens) computes numTokens * PRICE_PER_TOKEN without overflow check,
 * allowing an attacker to buy ~2^256/10^18 tokens for < 1 ETH and drain the pool via sell().
 */
contract CTETokenSaleHarness {
    mapping(address => uint256) public balanceOf;
    uint256 public constant PRICE_PER_TOKEN = 1 ether;
    uint256 public initialPoolBalance;

    event Bought(address indexed buyer, uint256 numTokens, uint256 paid);
    event Sold(address indexed seller, uint256 numTokens, uint256 payout);

    constructor() public payable {
        // Seed initial pool via seedPool() or constructor value; keep 0-value deploy compatible with Echidna.
        initialPoolBalance = 0;
    }

    function seedPool() public payable {
        require(initialPoolBalance == 0 && msg.value >= 1 ether);
        initialPoolBalance = msg.value;
    }

    function buy(uint256 numTokens) public payable {
        require(initialPoolBalance >= 1 ether);
        require(msg.value == numTokens * PRICE_PER_TOKEN);

        balanceOf[msg.sender] += numTokens;
        emit Bought(msg.sender, numTokens, msg.value);
    }

    function sell(uint256 numTokens) public {
        require(balanceOf[msg.sender] >= numTokens);

        balanceOf[msg.sender] -= numTokens;
        uint256 payout = numTokens * PRICE_PER_TOKEN;
        msg.sender.transfer(payout);
        emit Sold(msg.sender, numTokens, payout);
    }

    function contractBalance() public view returns (uint256) {
        return address(this).balance;
    }

    /// @notice Original CTE TokenSale invariant: once seeded with >=1 ETH, contract balance never drops below 1 ETH.
    function echidna_pool_not_drained_below_seed() public view returns (bool) {
        if (initialPoolBalance < 1 ether) {
            return true;
        }
        return address(this).balance >= 1 ether;
    }
}
