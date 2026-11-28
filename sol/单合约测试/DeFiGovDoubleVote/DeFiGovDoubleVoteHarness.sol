// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * Representative DeFi Stateful Pattern: Snapshot-less Governance Double-Voting with Dynamic Proposal ID & Timelock.
 * Combines three cross-transaction dependencies:
 *   1. Dynamic bytes32 proposalId emitted by ProposalCreated event;
 *   2. Cross-account governance token transfer to vote twice with the same 1000 tokens (quorum = 1500);
 *   3. Block timestamp advancement (delay_seconds >= VOTING_PERIOD) before executeProposal().
 */
contract DeFiGovDoubleVoteHarness {
    address public constant HOLDER = 0x0000000000000000000000000000000000010000;
    uint256 public constant INITIAL_SUPPLY = 1000;
    uint256 public constant QUORUM = 1500;
    uint256 public constant VOTING_PERIOD = 3600;

    mapping(address => uint256) public balanceOf;
    uint256 public proposalNonce;

    struct Proposal {
        address proposer;
        uint256 createdAt;
        uint256 votesFor;
        bool executed;
    }

    mapping(bytes32 => Proposal) public proposals;
    mapping(bytes32 => mapping(address => bool)) public hasVoted;
    bool public quorumBypassed;

    event ProposalCreated(bytes32 indexed proposalId, address indexed proposer, uint256 createdAt);
    event Voted(bytes32 indexed proposalId, address indexed voter, uint256 weight, uint256 totalVotes);
    event ProposalExecuted(bytes32 indexed proposalId, uint256 totalVotes);

    constructor() {
        balanceOf[HOLDER] = INITIAL_SUPPLY;
    }

    function transfer(address to, uint256 amount) external {
        require(to != address(0) && amount > 0, "INVALID_TRANSFER");
        require(balanceOf[msg.sender] >= amount, "INSUFFICIENT_BALANCE");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
    }

    function createProposal(bytes32 salt) external returns (bytes32 proposalId) {
        require(balanceOf[msg.sender] > 0, "NO_VOTING_POWER");
        proposalNonce += 1;
        proposalId = keccak256(abi.encodePacked(msg.sender, proposalNonce, salt, block.timestamp));
        proposals[proposalId] = Proposal({
            proposer: msg.sender,
            createdAt: block.timestamp,
            votesFor: 0,
            executed: false
        });
        emit ProposalCreated(proposalId, msg.sender, block.timestamp);
    }

    function vote(bytes32 proposalId) external {
        Proposal storage p = proposals[proposalId];
        require(p.createdAt > 0, "PROPOSAL_NOT_FOUND");
        require(!p.executed, "ALREADY_EXECUTED");
        require(block.timestamp < p.createdAt + VOTING_PERIOD, "VOTING_ENDED");
        require(!hasVoted[proposalId][msg.sender], "ALREADY_VOTED");
        uint256 weight = balanceOf[msg.sender];
        require(weight > 0, "ZERO_WEIGHT");

        hasVoted[proposalId][msg.sender] = true;
        p.votesFor += weight;
        emit Voted(proposalId, msg.sender, weight, p.votesFor);
    }

    function executeProposal(bytes32 proposalId) external {
        Proposal storage p = proposals[proposalId];
        require(p.createdAt > 0, "PROPOSAL_NOT_FOUND");
        require(!p.executed, "ALREADY_EXECUTED");
        require(block.timestamp >= p.createdAt + VOTING_PERIOD, "VOTING_STILL_ACTIVE");
        require(p.votesFor >= QUORUM, "QUORUM_NOT_MET");

        p.executed = true;
        quorumBypassed = true;
        emit ProposalExecuted(proposalId, p.votesFor);
    }

    /// @notice Total governance supply is 1000 while quorum is 1500; no proposal should ever be executable.
    function echidna_quorum_cannot_be_exceeded() public view returns (bool) {
        return !quorumBypassed;
    }
}
