// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title Roles
/// @notice Minimal two-tier access control shared by every contract in the RWA
///         tokenization demo: a single `owner` (governance) and a set of
///         `agents` (operational actors). This mirrors the owner/agent split of
///         ERC-3643 (T-REX) without vendoring the full suite.
/// @dev The deployer is set as BOTH owner and the first agent in the
///      constructor, so a freshly deployed contract is immediately operable by
///      the deployer alone — which is exactly how this demo is wired: every
///      privileged role resolves to the single deployer address.
abstract contract Roles {
    /*//////////////////////////////////////////////////////////////
                                 ERRORS
    //////////////////////////////////////////////////////////////*/

    /// @notice The caller is not the owner.
    error NotOwner(address caller);
    /// @notice The caller does not hold the agent role.
    error NotAgent(address caller);
    /// @notice A zero address was supplied where a real account is required.
    error ZeroAddress();

    /*//////////////////////////////////////////////////////////////
                                 EVENTS
    //////////////////////////////////////////////////////////////*/

    /// @notice Emitted when ownership moves from `previousOwner` to `newOwner`.
    /// @param previousOwner The outgoing owner. Zero on the constructor's emission, which
    ///        is what makes the deploy transaction itself the auditable origin of ownership.
    /// @param newOwner The incoming owner.
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    /// @notice Emitted when `account` is granted (`enabled=true`) or revoked the agent role.
    /// @param account The account whose agent role changed.
    /// @param enabled True when the role was granted, false when revoked. Emitted on every
    ///        call, including a no-op re-grant, so the event log is a complete history of
    ///        intent rather than only of changes.
    event AgentSet(address indexed account, bool enabled);

    /*//////////////////////////////////////////////////////////////
                                 STORAGE
    //////////////////////////////////////////////////////////////*/

    /// @notice The governance account. May transfer ownership and manage agents.
    address public owner;
    /// @notice Operational actors permitted to take agent-gated actions.
    mapping(address account => bool isAgent) public agents;

    /*//////////////////////////////////////////////////////////////
                                MODIFIERS
    //////////////////////////////////////////////////////////////*/

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner(msg.sender);
        _;
    }

    modifier onlyAgent() {
        if (!agents[msg.sender]) revert NotAgent(msg.sender);
        _;
    }

    /*//////////////////////////////////////////////////////////////
                               CONSTRUCTOR
    //////////////////////////////////////////////////////////////*/

    /// @notice Sets the deploying governance account as owner and first agent.
    /// @param initialOwner The account that becomes owner and the first agent. Rejected if
    ///        zero: a contract with no owner could never grant an agent, so the whole
    ///        agent-gated surface would be permanently unreachable.
    constructor(address initialOwner) {
        if (initialOwner == address(0)) revert ZeroAddress();
        owner = initialOwner;
        agents[initialOwner] = true;
        emit OwnershipTransferred(address(0), initialOwner);
        emit AgentSet(initialOwner, true);
    }

    /*//////////////////////////////////////////////////////////////
                               GOVERNANCE
    //////////////////////////////////////////////////////////////*/

    /// @notice Transfer ownership to `newOwner`.
    /// @dev The new owner is NOT granted an agent role automatically; manage
    ///      that separately with {setAgent} if the new owner should also operate.
    /// @param newOwner The account to hand governance to. Rejected if zero — this contract
    ///        has no renounce path, so a zero transfer would be an irreversible mistake
    ///        rather than a deliberate abdication.
    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert ZeroAddress();
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    /// @notice Grant (`enabled=true`) or revoke the agent role for `account`.
    /// @param account The account to grant or revoke. Rejected if zero, so the agent
    ///        mapping can never record a role against the null address.
    /// @param enabled True to grant, false to revoke. Owner-only, and separate from
    ///        ownership: an agent operates, an owner governs.
    function setAgent(address account, bool enabled) external onlyOwner {
        if (account == address(0)) revert ZeroAddress();
        agents[account] = enabled;
        emit AgentSet(account, enabled);
    }
}
