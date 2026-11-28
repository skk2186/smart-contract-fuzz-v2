// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * Representative DeFi Stateful Pattern: Dynamic Hash-ID Timed Auction Accounting Leak.
 * Combines:
 *   1. Dynamic bytes32 auctionId emitted by AuctionCreated event (Layer 1 binding);
 *   2. Multi-bidder competition (Account A bids -> Account B outbids);
 *   3. Block timestamp advancement (delay_seconds >= duration) to settle();
 *   4. Bug: withdrawOutbid() does not zero pendingReturns[auctionId][msg.sender] before/after payout,
 *      or allows double withdrawal using the settled pool balance.
 */
contract DeFiAuctionTimeIdHarness {
    struct Auction {
        address seller;
        uint256 endTime;
        address highestBidder;
        uint256 highestBid;
        bool settled;
    }

    uint256 public auctionNonce;
    mapping(bytes32 => Auction) public auctions;
    mapping(bytes32 => mapping(address => uint256)) public pendingReturns;
    uint256 public totalDeposited;
    uint256 public totalPaidOut;

    event AuctionCreated(bytes32 indexed auctionId, address indexed seller, uint256 endTime);
    event BidPlaced(bytes32 indexed auctionId, address indexed bidder, uint256 amount);
    event AuctionSettled(bytes32 indexed auctionId, address indexed winner, uint256 winningBid);
    event OutbidWithdrawn(bytes32 indexed auctionId, address indexed bidder, uint256 amount);

    function createAuction(uint256 duration, bytes32 salt) external returns (bytes32 auctionId) {
        require(duration >= 600 && duration <= 7200, "INVALID_DURATION");
        auctionNonce += 1;
        auctionId = keccak256(abi.encodePacked(msg.sender, auctionNonce, salt, block.timestamp));
        auctions[auctionId] = Auction({
            seller: msg.sender,
            endTime: block.timestamp + duration,
            highestBidder: address(0),
            highestBid: 0,
            settled: false
        });
        emit AuctionCreated(auctionId, msg.sender, block.timestamp + duration);
    }

    function bid(bytes32 auctionId) external payable {
        Auction storage a = auctions[auctionId];
        require(a.endTime > 0, "AUCTION_NOT_FOUND");
        require(block.timestamp < a.endTime, "AUCTION_ENDED");
        require(msg.value >= 1 ether && msg.value > a.highestBid, "BID_TOO_LOW");

        if (a.highestBidder != address(0)) {
            pendingReturns[auctionId][a.highestBidder] += a.highestBid;
        }
        a.highestBidder = msg.sender;
        a.highestBid = msg.value;
        totalDeposited += msg.value;
        emit BidPlaced(auctionId, msg.sender, msg.value);
    }

    function settle(bytes32 auctionId) external {
        Auction storage a = auctions[auctionId];
        require(a.endTime > 0, "AUCTION_NOT_FOUND");
        require(block.timestamp >= a.endTime, "AUCTION_NOT_ENDED");
        require(!a.settled, "ALREADY_SETTLED");
        require(a.highestBidder != address(0), "NO_BIDS");

        a.settled = true;
        // Bug: mistakenly credits seller AND leaves highestBid withdrawable via pendingReturns for winner
        pendingReturns[auctionId][a.highestBidder] += a.highestBid;
        totalPaidOut += a.highestBid;
        (bool ok, ) = payable(a.seller).call{value: a.highestBid}("");
        require(ok, "SELLER_PAYOUT_FAILED");
        emit AuctionSettled(auctionId, a.highestBidder, a.highestBid);
    }

    function withdrawOutbid(bytes32 auctionId) external {
        uint256 amount = pendingReturns[auctionId][msg.sender];
        require(amount > 0, "NOTHING_TO_WITHDRAW");
        pendingReturns[auctionId][msg.sender] = 0;
        totalPaidOut += amount;
        (bool ok, ) = payable(msg.sender).call{value: amount}("");
        require(ok, "WITHDRAW_FAILED");
        emit OutbidWithdrawn(auctionId, msg.sender, amount);
    }

    /// @notice Total ETH paid out across bids and settlements must never exceed total ETH deposited.
    function echidna_auction_accounting_conserved() public view returns (bool) {
        return totalPaidOut <= totalDeposited;
    }
}
