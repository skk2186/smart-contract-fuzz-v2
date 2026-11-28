// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * Representative DeFi Stateful Pattern: MultiSig Threshold Bypass via Revoke Counter Desync.
 * 2-of-3 multisig where revokeConfirmation() clears isConfirmed[txId][msg.sender]
 * without decrementing tx.confirmationCount, allowing a single signer to reach threshold=2:
 *   submitTx -> confirmTx -> revokeConfirmation -> confirmTx -> executeTx.
 */
contract DeFiMultiSigBypassHarness {
    address public constant SIGNER_1 = 0x0000000000000000000000000000000000010000;
    address public constant SIGNER_2 = 0x0000000000000000000000000000000000020000;
    address public constant SIGNER_3 = 0x0000000000000000000000000000000000030000;
    uint256 public constant THRESHOLD = 2;

    struct TxProposal {
        address to;
        uint256 amount;
        uint256 confirmationCount;
        bool executed;
    }

    uint256 public txNonce;
    mapping(bytes32 => TxProposal) public txs;
    mapping(bytes32 => mapping(address => bool)) public isConfirmed;
    mapping(bytes32 => uint256) public distinctSignerCount;
    mapping(bytes32 => mapping(address => bool)) public everConfirmed;
    bool public singleSignerExecuted;

    event TxSubmitted(bytes32 indexed txId, address indexed to, uint256 amount);
    event TxConfirmed(bytes32 indexed txId, address indexed signer, uint256 count);
    event TxRevoked(bytes32 indexed txId, address indexed signer);
    event TxExecuted(bytes32 indexed txId, address indexed to, uint256 amount);

    modifier onlySigner() {
        require(msg.sender == SIGNER_1 || msg.sender == SIGNER_2 || msg.sender == SIGNER_3, "NOT_SIGNER");
        _;
    }

    function submitTx(address to, uint256 amount, bytes32 salt) external onlySigner returns (bytes32 txId) {
        require(to != address(0) && amount > 0, "INVALID_TX");
        txNonce += 1;
        txId = keccak256(abi.encodePacked(msg.sender, to, amount, txNonce, salt));
        txs[txId] = TxProposal({
            to: to,
            amount: amount,
            confirmationCount: 0,
            executed: false
        });
        emit TxSubmitted(txId, to, amount);
    }

    function confirmTx(bytes32 txId) external onlySigner {
        TxProposal storage t = txs[txId];
        require(t.amount > 0, "TX_NOT_FOUND");
        require(!t.executed, "ALREADY_EXECUTED");
        require(!isConfirmed[txId][msg.sender], "ALREADY_CONFIRMED");

        isConfirmed[txId][msg.sender] = true;
        t.confirmationCount += 1;
        if (!everConfirmed[txId][msg.sender]) {
            everConfirmed[txId][msg.sender] = true;
            distinctSignerCount[txId] += 1;
        }
        emit TxConfirmed(txId, msg.sender, t.confirmationCount);
    }

    /// @notice Bug: clears isConfirmed flag but forgets to decrement t.confirmationCount!
    function revokeConfirmation(bytes32 txId) external onlySigner {
        TxProposal storage t = txs[txId];
        require(t.amount > 0, "TX_NOT_FOUND");
        require(!t.executed, "ALREADY_EXECUTED");
        require(isConfirmed[txId][msg.sender], "NOT_CONFIRMED");

        isConfirmed[txId][msg.sender] = false;
        emit TxRevoked(txId, msg.sender);
    }

    function executeTx(bytes32 txId) external onlySigner {
        TxProposal storage t = txs[txId];
        require(t.amount > 0, "TX_NOT_FOUND");
        require(!t.executed, "ALREADY_EXECUTED");
        require(t.confirmationCount >= THRESHOLD, "INSUFFICIENT_CONFIRMATIONS");

        t.executed = true;
        if (distinctSignerCount[txId] < THRESHOLD) {
            singleSignerExecuted = true;
        }
        emit TxExecuted(txId, t.to, t.amount);
    }

    /// @notice No multisig transaction may execute without at least 2 distinct signers confirming.
    function echidna_threshold_requires_distinct_signers() public view returns (bool) {
        return !singleSignerExecuted;
    }
}
