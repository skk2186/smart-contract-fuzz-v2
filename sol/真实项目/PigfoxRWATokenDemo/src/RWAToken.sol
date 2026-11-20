// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Roles} from "./Roles.sol";
import {IIdentityRegistry} from "./interfaces/IIdentityRegistry.sol";
import {IRWAToken} from "./interfaces/IRWAToken.sol";

/// @title RWAToken
/// @notice A fractional ERC-20 representing shares of a real-world asset, with
///         ERC-3643-style compliance hooks: every acquisition of tokens is
///         gated on KYC verification. Minting requires the recipient to be
///         verified; transfers require BOTH parties to be verified.
/// @dev Hand-rolled minimal ERC-20 (no external token library vendored). The
///      compliance checks live in {mint} and {_transfer}; burns (redemption)
///      are restricted to the configured {redeemer} and are exempt from the
///      verification hooks because they only ever reduce a balance.
contract RWAToken is Roles, IRWAToken {
    /*//////////////////////////////////////////////////////////////
                                 ERRORS
    //////////////////////////////////////////////////////////////*/

    /// @notice The sender of a transfer is not KYC-verified.
    error SenderNotVerified(address account);
    /// @notice The recipient of a mint or transfer is not KYC-verified.
    error RecipientNotVerified(address account);
    /// @notice `account` holds fewer tokens than the operation requires.
    error InsufficientBalance(address account, uint256 balance, uint256 needed);
    /// @notice `spender` has less allowance from `owner` than the operation requires.
    error InsufficientAllowance(address owner, address spender, uint256 allowance, uint256 needed);
    /// @notice Only the configured redeemer may burn tokens.
    error NotRedeemer(address caller);

    /*//////////////////////////////////////////////////////////////
                                 EVENTS
    //////////////////////////////////////////////////////////////*/

    /// @notice ERC-20 transfer event (mint = from zero, burn = to zero).
    /// @param from The sender; zero when the transfer is a mint.
    /// @param to The recipient; zero when the transfer is a burn.
    /// @param value The amount moved. NOT indexed, because ERC-20 fixes this signature —
    ///        indexing it would change the topic layout and break every standard consumer.
    event Transfer(address indexed from, address indexed to, uint256 value);
    /// @notice ERC-20 approval event.
    /// @param owner The account whose tokens may now be pulled.
    /// @param spender The account permitted to pull them.
    /// @param value The new allowance, which replaces any previous one rather than adding to it.
    event Approval(address indexed owner, address indexed spender, uint256 value);
    /// @notice Emitted when the redeemer (the Redemption contract) is configured.
    /// @param redeemer The only address that may call `burnFrom`. Re-emitted on every
    ///        change, so the log shows which contract held burn authority at any block.
    event RedeemerSet(address indexed redeemer);

    /*//////////////////////////////////////////////////////////////
                                METADATA
    //////////////////////////////////////////////////////////////*/

    /// @notice ERC-20 token name.
    string public name;
    /// @notice ERC-20 token symbol.
    string public symbol;
    /// @notice ERC-20 decimals. Fixed at 18 for fractional shares.
    uint8 public constant decimals = 18;

    /*//////////////////////////////////////////////////////////////
                                 STORAGE
    //////////////////////////////////////////////////////////////*/

    /// @notice Total tokens in existence. Equals the sum of all balances.
    uint256 public totalSupply;
    mapping(address account => uint256 balance) private _balances;
    mapping(address owner => mapping(address spender => uint256 amount)) private _allowances;

    /// @notice The KYC whitelist consulted on every mint and transfer.
    IIdentityRegistry public immutable identityRegistry;
    /// @notice The Redemption contract permitted to burn tokens. Zero until set.
    address public redeemer;

    /// @notice Binds the token to its KYC whitelist and sets the deployer as owner.
    /// @dev `identityRegistry_` is stored as an `immutable`: the compliance gate holders
    ///      are judged against is fixed for the life of the token, so it cannot be swapped
    ///      for a permissive one after balances exist.
    /// @param name_ ERC-20 name.
    /// @param symbol_ ERC-20 symbol.
    /// @param identityRegistry_ The KYC whitelist address (non-zero).
    /// @param initialOwner The deployer; owner and first (mint) agent.
    constructor(string memory name_, string memory symbol_, address identityRegistry_, address initialOwner)
        Roles(initialOwner)
    {
        if (identityRegistry_ == address(0)) revert ZeroAddress();
        name = name_;
        symbol = symbol_;
        identityRegistry = IIdentityRegistry(identityRegistry_);
    }

    /*//////////////////////////////////////////////////////////////
                                  VIEWS
    //////////////////////////////////////////////////////////////*/

    /// @notice The token balance of `account`.
    /// @param account The address to read.
    /// @return The balance. Unaffected by verification status: losing verification blocks
    ///         future movement, it never confiscates a balance.
    function balanceOf(address account) external view override returns (uint256) {
        return _balances[account];
    }

    /// @notice The remaining tokens `spender` may pull from `holder`.
    /// @param holder The account whose tokens would be pulled.
    /// @param spender The account permitted to pull them.
    /// @return The remaining allowance. An allowance is not a promise the transfer will
    ///         succeed — both parties must still be verified when it is spent.
    function allowance(address holder, address spender) external view returns (uint256) {
        return _allowances[holder][spender];
    }

    /*//////////////////////////////////////////////////////////////
                                 WIRING
    //////////////////////////////////////////////////////////////*/

    /// @notice Configure the redeemer (the Redemption contract) permitted to burn.
    /// @param redeemer_ The address granted burn authority. Rejected if zero. Owner-only
    ///        and deliberately re-settable, unlike the identity registry: the redemption
    ///        contract is replaceable operational wiring, whereas the compliance gate is
    ///        the token's guarantee and is fixed at construction.
    function setRedeemer(address redeemer_) external onlyOwner {
        if (redeemer_ == address(0)) revert ZeroAddress();
        redeemer = redeemer_;
        emit RedeemerSet(redeemer_);
    }

    /*//////////////////////////////////////////////////////////////
                             MINT (COMPLIANT)
    //////////////////////////////////////////////////////////////*/

    /// @notice Mint `amount` tokens to `to`. The recipient must be KYC-verified.
    /// @param to The recipient. Must be whitelisted at this moment, checked against the
    ///        registry rather than any cached list.
    /// @param amount The quantity to create, added to `totalSupply`.
    function mint(address to, uint256 amount) external onlyAgent {
        if (to == address(0)) revert ZeroAddress();
        if (!identityRegistry.isVerified(to)) revert RecipientNotVerified(to);
        totalSupply += amount;
        _balances[to] += amount;
        emit Transfer(address(0), to, amount);
    }

    /*//////////////////////////////////////////////////////////////
                               ERC-20 WRITES
    //////////////////////////////////////////////////////////////*/

    /// @notice Approve `spender` to pull up to `amount` of the caller's tokens.
    /// @param spender The account permitted to pull. Rejected if zero.
    /// @param amount The new allowance, replacing any previous value outright.
    /// @return Always true. The bool exists because ERC-20 specifies it; failures revert.
    function approve(address spender, uint256 amount) external returns (bool) {
        if (spender == address(0)) revert ZeroAddress();
        _allowances[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    /// @notice Transfer `amount` tokens to `to`. Both parties must be verified.
    /// @param to The recipient, which must be whitelisted at this moment.
    /// @param amount The quantity to move.
    /// @return Always true; a non-compliant or underfunded transfer reverts rather than
    ///         returning false, so a caller cannot mistake refusal for success. This
    ///         reverting transfer is the demo's compliance showcase.
    function transfer(address to, uint256 amount) external returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    /// @notice Transfer `amount` from `from` to `to` using the caller's allowance.
    ///         Both `from` and `to` must be verified.
    /// @param from The account whose tokens move; its verification is re-checked here, so
    ///        an allowance granted while verified is unusable once it is removed.
    /// @param to The recipient, which must also be verified.
    /// @param amount The quantity to move, also deducted from the caller's allowance.
    /// @return Always true; refusals revert.
    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        _spendAllowance(from, msg.sender, amount);
        _transfer(from, to, amount);
        return true;
    }

    /*//////////////////////////////////////////////////////////////
                             BURN (REDEMPTION)
    //////////////////////////////////////////////////////////////*/

    /// @notice Burn `amount` tokens held by `from`. Restricted to the redeemer.
    /// @dev Exempt from the verification hooks: a burn only reduces a balance and
    ///      can never create a holding for a non-verified address.
    /// @param from The holder whose tokens are destroyed. Deliberately NOT required to be
    ///        verified: a holder who lost verification must still be able to redeem out,
    ///        and blocking that would strand their tokens permanently.
    /// @param amount The quantity to burn, also deducted from `totalSupply`.
    function burnFrom(address from, uint256 amount) external override {
        if (msg.sender != redeemer) revert NotRedeemer(msg.sender);
        uint256 bal = _balances[from];
        if (bal < amount) revert InsufficientBalance(from, bal, amount);
        unchecked {
            _balances[from] = bal - amount;
            totalSupply -= amount;
        }
        emit Transfer(from, address(0), amount);
    }

    /*//////////////////////////////////////////////////////////////
                                INTERNALS
    //////////////////////////////////////////////////////////////*/

    /// @dev Shared transfer path enforcing the both-parties-verified hook.
    function _transfer(address from, address to, uint256 amount) internal {
        if (to == address(0)) revert ZeroAddress();
        if (!identityRegistry.isVerified(from)) revert SenderNotVerified(from);
        if (!identityRegistry.isVerified(to)) revert RecipientNotVerified(to);
        uint256 bal = _balances[from];
        if (bal < amount) revert InsufficientBalance(from, bal, amount);
        unchecked {
            _balances[from] = bal - amount;
            _balances[to] += amount;
        }
        emit Transfer(from, to, amount);
    }

    /// @dev Deduct `amount` from the (`holder`,`spender`) allowance. An allowance
    ///      of `type(uint256).max` is treated as infinite and never decremented.
    function _spendAllowance(address holder, address spender, uint256 amount) internal {
        uint256 current = _allowances[holder][spender];
        if (current != type(uint256).max) {
            if (current < amount) revert InsufficientAllowance(holder, spender, current, amount);
            unchecked {
                _allowances[holder][spender] = current - amount;
            }
        }
    }
}
