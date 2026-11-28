// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * Representative DeFi Stateful Pattern: Dynamic Hash-ID Escrow State-Machine Double-Claim.
 * Directly stresses Layer 1 runtime event-ID binding (bytes32 escrowId cannot be guessed statically)
 * combined with multi-role workflow (depositor -> approveRelease -> beneficiary claim + cancel bug).
 */
contract DeFiEscrowHashIdHarness {
    struct Escrow {
        address depositor;
        address beneficiary;
        uint256 amount;
        bool approved;
        bool claimed;
        bool cancelled;
    }

    uint256 public escrowNonce;
    mapping(bytes32 => Escrow) public escrows;
    uint256 public totalDeposited;
    uint256 public totalPaidOut;

    event EscrowCreated(bytes32 indexed escrowId, address indexed depositor, address indexed beneficiary, uint256 amount);
    event EscrowApproved(bytes32 indexed escrowId);
    event EscrowClaimed(bytes32 indexed escrowId, address indexed beneficiary, uint256 amount);
    event EscrowCancelled(bytes32 indexed escrowId, address indexed depositor, uint256 amount);

    function createEscrow(address beneficiary, bytes32 salt) external payable returns (bytes32 escrowId) {
        require(beneficiary != address(0) && beneficiary != msg.sender, "INVALID_BENEFICIARY");
        require(msg.value >= 1 ether, "MIN_ESCROW_1_ETH");
        escrowNonce += 1;
        escrowId = keccak256(abi.encodePacked(msg.sender, beneficiary, escrowNonce, salt, block.timestamp));
        escrows[escrowId] = Escrow({
            depositor: msg.sender,
            beneficiary: beneficiary,
            amount: msg.value,
            approved: false,
            claimed: false,
            cancelled: false
        });
        totalDeposited += msg.value;
        emit EscrowCreated(escrowId, msg.sender, beneficiary, msg.value);
    }

    function approveRelease(bytes32 escrowId) external {
        Escrow storage e = escrows[escrowId];
        require(e.amount > 0, "ESCROW_NOT_FOUND");
        require(msg.sender == e.depositor, "NOT_DEPOSITOR");
        require(!e.cancelled && !e.claimed, "ESCROW_CLOSED");
        e.approved = true;
        emit EscrowApproved(escrowId);
    }

    function claim(bytes32 escrowId) external {
        Escrow storage e = escrows[escrowId];
        require(e.amount > 0, "ESCROW_NOT_FOUND");
        require(msg.sender == e.beneficiary, "NOT_BENEFICIARY");
        require(e.approved, "NOT_APPROVED");
        require(!e.claimed, "ALREADY_CLAIMED");

        e.claimed = true;
        totalPaidOut += e.amount;
        (bool ok, ) = payable(e.beneficiary).call{value: e.amount}("");
        require(ok, "PAYOUT_FAILED");
        emit EscrowClaimed(escrowId, e.beneficiary, e.amount);
    }

    /// @notice Bug: cancelEscrow checks !e.cancelled but forgets to check !e.claimed!
    function cancelEscrow(bytes32 escrowId) external {
        Escrow storage e = escrows[escrowId];
        require(e.amount > 0, "ESCROW_NOT_FOUND");
        require(msg.sender == e.depositor, "NOT_DEPOSITOR");
        require(!e.cancelled, "ALREADY_CANCELLED");

        e.cancelled = true;
        totalPaidOut += e.amount;
        (bool ok, ) = payable(e.depositor).call{value: e.amount}("");
        require(ok, "REFUND_FAILED");
        emit EscrowCancelled(escrowId, e.depositor, e.amount);
    }

    /// @notice Accounting invariant: total ETH paid out across all escrows must never exceed total deposited.
    function echidna_escrow_solvency() public view returns (bool) {
        return totalPaidOut <= totalDeposited;
    }
}
