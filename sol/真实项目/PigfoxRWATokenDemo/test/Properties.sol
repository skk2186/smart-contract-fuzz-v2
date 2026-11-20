// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {PigfoxProperties} from "pipeline/PigfoxProperties.sol";

import {AssetRegistry} from "../src/AssetRegistry.sol";
import {IdentityRegistry} from "../src/IdentityRegistry.sol";
import {PriceOracle} from "../src/PriceOracle.sol";
import {Redemption} from "../src/Redemption.sol";
import {RWAToken} from "../src/RWAToken.sol";

import {Actor} from "./Actor.sol";

/// @title Properties — the RWA system's invariants, in one place.
/// @notice A single property harness driven by all three engines: Foundry's
///         invariant runner (via {InvariantsTest}), Echidna and Medusa. It
///         deploys the whole system, holds the owner and agent roles, and exposes
///         action functions the fuzzers call plus the `echidna_*` predicates.
///
/// @dev    THE HARNESS COVERS ALL FIVE CONTRACTS, not three. An earlier version
///         fuzzed the token, the identity registry and the oracle, and left
///         `AssetRegistry` and `Redemption` to unit tests alone — which meant the
///         redemption ledger, the part of this system that actually destroys
///         value, had no invariant on it at all.
///
/// @dev    WHY THERE ARE ACTOR CONTRACTS.
///         `Redemption.requestRedemption` records `msg.sender` as the holder and
///         burns that account's tokens. Neither fuzzer has cheatcodes, so the
///         only way to have a redemption arrive from someone other than the
///         harness is to own a contract at that address and call through it.
///         Four actors mean the ledger invariants see four distinct holders
///         instead of one, which is the difference between testing the ledger and
///         testing one row of it.
///
/// @dev    WHY THE LEDGER CHECKS ARE EAGER.
///         A predicate that walks every request is quadratic over a campaign —
///         the fuzzer evaluates predicates after every single call — and it
///         spends the budget re-reading old state instead of reaching new state.
///         So each entry point verifies its own effect IMMEDIATELY and trips a
///         sticky flag, and additionally re-verifies ONE older request
///         round-robin. Predicates then read the flags in O(1). The comparison
///         happens at the moment of divergence, on the input that caused it.
///
/// @dev    `PHANTOM` is deliberately never KYC-verified: no action can ever give
///         it a balance, which is the transfer-hook invariant made concrete.
contract Properties is PigfoxProperties {
    AssetRegistry internal immutable ASSETS;
    IdentityRegistry internal immutable IDENTITY;
    PriceOracle internal immutable ORACLE;
    Redemption internal immutable REDEMPTION;
    RWAToken internal immutable TOKEN;

    uint256 internal constant NUM_HOLDERS = 4;
    /// @notice The one address that is never KYC-verified.
    address internal constant PHANTOM = address(0xBAD);

    Actor[NUM_HOLDERS] internal actors;
    address[NUM_HOLDERS] internal holders;
    mapping(address => bool) internal isHolder;

    // --- ghost state ---------------------------------------------------------
    // Counts prove the run was not inert; the totals are what the conservation
    // invariant is stated against.

    uint256 internal ghostMints;
    uint256 internal ghostTransfers;
    uint256 internal ghostBurns;
    uint256 internal ghostMintedTotal;
    uint256 internal ghostBurnedTotal;
    uint256 internal ghostRedeemedTotal;
    uint256 internal ghostSettlements;
    uint256 internal lastOracleStamp;

    /// @dev Round-robin cursor for re-verifying an older redemption request.
    uint256 internal requestCursor;

    /// @dev What the harness believes each request holds, recorded at the moment
    ///      it was created. Compared against the contract's own record later —
    ///      asking the contract what it should say would let a bug agree with
    ///      itself.
    mapping(uint256 => address) internal expectedHolder;
    mapping(uint256 => uint256) internal expectedAmount;
    mapping(uint256 => uint256) internal expectedAsset;
    mapping(uint256 => bool) internal expectedSettled;

    // --- sticky flags --------------------------------------------------------

    /// @notice Set if the redemption ledger ever disagreed with what the harness
    ///         asked for, or if ids stopped being sequential and gapless.
    bool public ledgerInconsistent;

    /// @notice Set if a redemption ever SUCCEEDED against an asset that was not
    ///         Active at the moment of the call. This is the access-control claim
    ///         the redemption path rests on.
    bool public inactiveAssetRedeemed;

    /// @notice Set if the asset registry ever reported an id below `assetCount`
    ///         as unknown, or an asset's status as the zero value after
    ///         registration.
    bool public assetRegistryInconsistent;

    constructor() {
        IDENTITY = new IdentityRegistry(address(this));
        TOKEN = new RWAToken("RWA Property", "RWAP", address(IDENTITY), address(this));
        ORACLE = new PriceOracle(address(this));
        ASSETS = new AssetRegistry(address(this));
        REDEMPTION = new Redemption(address(TOKEN), address(ASSETS), address(this));

        IDENTITY.setToken(address(TOKEN));

        // The Redemption contract is the ONLY redeemer, which is the production
        // wiring. Burns therefore reach the token exclusively through a recorded
        // redemption request — there is no side door for the harness to burn
        // through, so `ghostBurnedTotal` and the ledger cannot drift apart by
        // construction rather than by promise.
        TOKEN.setRedeemer(address(REDEMPTION));

        // The harness itself must be verified to hold and distribute tokens.
        IDENTITY.registerIdentity(address(this));
        for (uint256 i = 0; i < NUM_HOLDERS; i++) {
            Actor a = new Actor();
            actors[i] = a;
            holders[i] = address(a);
            isHolder[address(a)] = true;
            IDENTITY.registerIdentity(address(a));
        }
        // PHANTOM is intentionally NOT registered.
    }

    /*//////////////////////////////////////////////////////////////
                              DECLARATION
    //////////////////////////////////////////////////////////////*/

    /// @inheritdoc PigfoxProperties
    function pigfoxPropertyCount() public pure override returns (uint256) {
        return 6;
    }

    /// @inheritdoc PigfoxProperties
    function pigfoxHarnessDescription() public pure override returns (string memory) {
        return "supply conservation, KYC gating, oracle monotonicity, and a gapless redemption ledger";
    }

    /*//////////////////////////////////////////////////////////////
                                ACTIONS
    //////////////////////////////////////////////////////////////*/

    /// @notice Mint bounded tokens to the harness (a verified holder).
    function mintToSelf(uint256 amount) public {
        amount = _bound(amount);
        TOKEN.mint(address(this), amount);
        ghostMints++;
        ghostMintedTotal += amount;
        _afterCall();
    }

    /// @notice Mint bounded tokens directly to a verified holder.
    function mintToHolder(uint256 who, uint256 amount) public {
        amount = _bound(amount);
        TOKEN.mint(holders[who % NUM_HOLDERS], amount);
        ghostMints++;
        ghostMintedTotal += amount;
        _afterCall();
    }

    /// @notice Move tokens from the harness to a verified holder.
    function distribute(uint256 who, uint256 amount) public {
        uint256 bal = TOKEN.balanceOf(address(this));
        if (bal == 0) return;
        amount = amount % (bal + 1);
        TOKEN.transfer(holders[who % NUM_HOLDERS], amount);
        ghostTransfers++;
        _afterCall();
    }

    /// @notice Attempt to mint to the never-verified PHANTOM. Must always revert.
    function tryMintPhantom(uint256 amount) public {
        amount = _bound(amount);
        try TOKEN.mint(PHANTOM, amount) {
            // A successful mint to PHANTOM would break the transfer-hook
            // invariant, and `echidna_unverified_never_holds` would catch it a
            // moment later. Failing here as well makes the counterexample name
            // the call that did it.
            revert("phantom mint succeeded");
        } catch {
            // expected
        }
        _afterCall();
    }

    /// @notice Push a bounded price; records the stamp for the monotonic check.
    function pushPrice(uint256 p) public {
        ORACLE.setPrice(p % 1_000_000);
        lastOracleStamp = ORACLE.updatedAt();
        _afterCall();
    }

    /// @notice Register a new asset. Starts Active.
    function registerAsset(uint256 seed) public {
        uint256 idBefore = ASSETS.assetCount();
        uint256 id = ASSETS.registerAsset(keccak256(abi.encode("doc", seed)), "ipfs://property");

        if (id != idBefore || ASSETS.assetCount() != idBefore + 1) assetRegistryInconsistent = true;
        if (!ASSETS.isActive(id)) assetRegistryInconsistent = true;

        _afterCall();
    }

    /// @notice Move a registered asset through its lifecycle. Reaching the
    ///         non-Active statuses is what makes the "a redemption needs an active
    ///         asset" property testable at all.
    function setAssetStatus(uint256 which, uint256 status) public {
        uint256 count = ASSETS.assetCount();
        if (count == 0) return;
        uint256 id = which % count;

        // 1..3 — Active, Suspended, Redeemed. Zero (`None`) is rejected by the
        // contract by design and is exercised by the unit tests, not here.
        AssetRegistry.Status s = AssetRegistry.Status(1 + (status % 3));
        ASSETS.setAssetStatus(id, s);

        if (ASSETS.getAsset(id).status != s) assetRegistryInconsistent = true;
        if (ASSETS.isActive(id) != (s == AssetRegistry.Status.Active)) assetRegistryInconsistent = true;

        _afterCall();
    }

    /// @notice A holder redeems against an arbitrary asset, active or not.
    /// @dev    This is the entry point that tests the GUARD: `assetId` is chosen
    ///         without regard to status, so the fuzzer regularly attempts a
    ///         redemption against a Suspended or Redeemed asset and the call must
    ///         be refused. {redeemFromActiveAsset} is the one that reliably drives
    ///         the ledger. Splitting them is deliberate — a single entry point
    ///         that picked an active asset would never test the refusal, and one
    ///         that picked at random left whole campaigns with zero successful
    ///         redemptions, which is how three of the six predicates ended up
    ///         vacuously true.
    function redeem(uint256 who, uint256 which, uint256 amount) public {
        uint256 assetCount = _ensureAnAssetExists();
        uint256 index = who % NUM_HOLDERS;
        _redeemAgainst(index, which % assetCount, amount);
    }

    /// @notice A holder redeems against an asset that IS Active.
    /// @dev    Guarantees the redemption ledger is actually exercised. Without it
    ///         a sequence has to land `registerAsset`, `mintToHolder` and `redeem`
    ///         in the right order, against an asset nothing has since suspended,
    ///         before a single request exists — and most sequences never do.
    function redeemFromActiveAsset(uint256 who, uint256 amount) public {
        uint256 assetId = _anActiveAsset();
        _redeemAgainst(who % NUM_HOLDERS, assetId, amount);
    }

    /// @dev The shared redemption path. The outcome is compared against what the
    ///      harness independently expected: it knows the balance and whether the
    ///      asset was active, so it knows whether the call ought to have
    ///      succeeded.
    function _redeemAgainst(uint256 index, uint256 assetId, uint256 amount) internal {
        address holder = holders[index];

        uint256 bal = _ensureHolderHasTokens(holder, amount);
        amount = 1 + (amount % bal); // 1..bal — zero is rejected by design

        bool wasActive = ASSETS.isActive(assetId);
        uint256 idBefore = REDEMPTION.requestCount();
        uint256 supplyBefore = TOKEN.totalSupply();

        (bool ok,) = actors[index]
        .call(address(REDEMPTION), abi.encodeCall(Redemption.requestRedemption, (assetId, amount)));

        if (ok && !wasActive) {
            // The claim the whole redemption path rests on: value is only ever
            // destroyed against an asset the registrar has marked Active.
            inactiveAssetRedeemed = true;
        }

        if (!ok) {
            // A redemption the harness expected to succeed did not. Nothing about
            // this call could legitimately fail: the asset was active, the holder
            // held the balance, and the amount is non-zero.
            if (wasActive) ledgerInconsistent = true;
            _afterCall();
            return;
        }

        ghostBurns++;
        ghostBurnedTotal += amount;
        ghostRedeemedTotal += amount;

        expectedHolder[idBefore] = holder;
        expectedAmount[idBefore] = amount;
        expectedAsset[idBefore] = assetId;
        expectedSettled[idBefore] = false;

        if (REDEMPTION.requestCount() != idBefore + 1) ledgerInconsistent = true;
        if (TOKEN.totalSupply() != supplyBefore - amount) ledgerInconsistent = true;
        _verifyRequest(idBefore);
        _verifyNoRequestBeyondTheCount();

        _afterCall();
    }

    /// @notice An agent settles a recorded redemption request.
    /// @dev    Creates one first if none exists, for the same reason
    ///         {redeemFromActiveAsset} exists: a `settle` scheduled before any
    ///         redemption in its sequence would otherwise return without touching
    ///         anything, and whole campaigns would never settle at all.
    function settle(uint256 which) public {
        if (REDEMPTION.requestCount() == 0) {
            _redeemAgainst(which % NUM_HOLDERS, _anActiveAsset(), which);
        }
        uint256 count = REDEMPTION.requestCount();
        if (count == 0) return; // the bootstrap redemption was refused; nothing to settle
        uint256 id = which % count;

        if (expectedSettled[id]) {
            // Already settled: the contract must refuse. A second settlement
            // succeeding would mean the off-chain leg could be claimed twice.
            try REDEMPTION.settleRedemption(id) {
                ledgerInconsistent = true;
            } catch {
                // expected
            }
        } else {
            REDEMPTION.settleRedemption(id);
            expectedSettled[id] = true;
            ghostSettlements++;
        }

        _verifyRequest(id);
        _afterCall();
    }

    /*//////////////////////////////////////////////////////////////
                              PROPERTIES
    //////////////////////////////////////////////////////////////*/

    /// @notice totalSupply always equals the sum of every account's balance.
    function echidna_supply_equals_sum_of_balances() public view returns (bool) {
        uint256 sum = TOKEN.balanceOf(address(this)) + TOKEN.balanceOf(PHANTOM);
        for (uint256 i = 0; i < NUM_HOLDERS; i++) {
            sum += TOKEN.balanceOf(holders[i]);
        }
        return sum == TOKEN.totalSupply();
    }

    /// @notice The never-verified PHANTOM can never hold a non-zero balance.
    function echidna_unverified_never_holds() public view returns (bool) {
        return TOKEN.balanceOf(PHANTOM) == 0;
    }

    /// @notice The oracle timestamp never moves backwards.
    function echidna_oracle_stamp_monotonic() public view returns (bool) {
        return ORACLE.updatedAt() >= lastOracleStamp;
    }

    /// @notice Everything minted, minus everything burned, is the supply.
    /// @dev    Stated against the harness's OWN running totals rather than
    ///         against anything the token reports, so a token that mis-accounts a
    ///         mint or a burn cannot satisfy this by being consistently wrong.
    ///         Burns reach the token only through `Redemption`, so this also
    ///         closes the redemption path.
    function echidna_supply_conserved() public view returns (bool) {
        return ghostMintedTotal - ghostBurnedTotal == TOKEN.totalSupply();
    }

    /// @notice The redemption ledger is gapless, sequential, records exactly what
    ///         was asked of it, and never settles the same request twice.
    function echidna_redemption_ledger_consistent() public view returns (bool) {
        return !ledgerInconsistent;
    }

    /// @notice Value is only ever destroyed against an Active asset.
    function echidna_redemption_requires_active_asset() public view returns (bool) {
        return !inactiveAssetRedeemed && !assetRegistryInconsistent;
    }

    /*//////////////////////////////////////////////////////////////
                            NON-INERTNESS VIEWS
    //////////////////////////////////////////////////////////////*/

    /// @notice Number of mints the fuzzer has driven; used by the non-inertness guard.
    function ghostMintsView() external view returns (uint256) {
        return ghostMints;
    }

    /// @notice Number of transfers the fuzzer has driven.
    function ghostTransfersView() external view returns (uint256) {
        return ghostTransfers;
    }

    /// @notice Number of burns the fuzzer has driven, all of them redemptions.
    function ghostBurnsView() external view returns (uint256) {
        return ghostBurns;
    }

    /// @notice Number of redemption requests settled.
    function ghostSettlementsView() external view returns (uint256) {
        return ghostSettlements;
    }

    /// @notice Total amount redeemed across every request.
    function ghostRedeemedTotalView() external view returns (uint256) {
        return ghostRedeemedTotal;
    }

    /*//////////////////////////////////////////////////////////////
                                HELPERS
    //////////////////////////////////////////////////////////////*/

    /// @dev Registers an asset if none exists, and returns the count.
    ///      Bootstrapping preconditions in the harness rather than waiting for the
    ///      fuzzer to stumble into the right order is what keeps the budget on the
    ///      ledger instead of on setup. Every bootstrap write is accounted for in
    ///      the ghost totals exactly as a fuzzer-driven one would be, so nothing
    ///      here can make an invariant true by hiding a mutation from it.
    function _ensureAnAssetExists() internal returns (uint256 count) {
        count = ASSETS.assetCount();
        if (count == 0) {
            ASSETS.registerAsset(keccak256("bootstrap-asset"), "ipfs://bootstrap");
            count = 1;
        }
    }

    /// @dev Returns an Active asset id, making one Active if none is.
    function _anActiveAsset() internal returns (uint256) {
        uint256 count = _ensureAnAssetExists();
        for (uint256 i = 0; i < count; i++) {
            if (ASSETS.isActive(i)) return i;
        }
        // Everything has been suspended or redeemed. Reactivating asset zero is a
        // legitimate registrar action, and the alternative — returning early — is
        // how a campaign quietly stops testing the ledger.
        ASSETS.setAssetStatus(0, AssetRegistry.Status.Active);
        return 0;
    }

    /// @dev Ensures `holder` has something to redeem, and returns the balance.
    function _ensureHolderHasTokens(address holder, uint256 seed) internal returns (uint256 bal) {
        bal = TOKEN.balanceOf(holder);
        if (bal == 0) {
            uint256 amount = 1 + _bound(seed);
            TOKEN.mint(holder, amount);
            ghostMints++;
            ghostMintedTotal += amount;
            bal = amount;
        }
    }

    /// @dev Runs after every action: re-verify ONE older request, round-robin.
    ///      O(1) per call, and over a campaign it re-reads every request many
    ///      times, interleaved with writes — which is what would catch a later
    ///      call corrupting an earlier record. Walking the whole ledger in a
    ///      predicate would do the same job quadratically.
    function _afterCall() internal {
        uint256 count = REDEMPTION.requestCount();
        if (count == 0) return;
        _verifyRequest(requestCursor % count);
        requestCursor++;
    }

    /// @dev Compares the contract's record against what the harness recorded when
    ///      the request was made.
    function _verifyRequest(uint256 id) internal {
        try REDEMPTION.getRequest(id) returns (Redemption.Request memory r) {
            if (
                !r.exists || r.holder != expectedHolder[id] || r.amount != expectedAmount[id]
                    || r.assetId != expectedAsset[id] || r.settled != expectedSettled[id]
                    || !isHolder[r.holder] || r.amount == 0
            ) {
                ledgerInconsistent = true;
            }
        } catch {
            // Every id below `requestCount` must exist. A revert here is a gap.
            ledgerInconsistent = true;
        }
    }

    /// @dev `requestCount` is also the next id, so nothing may exist at it yet.
    ///      Ids that ran ahead of the counter would break pagination silently.
    function _verifyNoRequestBeyondTheCount() internal {
        try REDEMPTION.getRequest(REDEMPTION.requestCount()) returns (Redemption.Request memory) {
            ledgerInconsistent = true;
        } catch {
            // expected
        }
    }

    function _bound(uint256 amount) internal pure returns (uint256) {
        // Keep amounts in a range that can never overflow uint256 supply.
        return amount % (1_000_000 ether);
    }
}
