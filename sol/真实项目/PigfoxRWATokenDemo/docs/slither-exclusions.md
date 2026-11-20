# Slither detector exclusions

**The exclusion list is no longer kept here.** Since this repo adopted the
[PIGFOX SOLIDITY PIPELINE v1](https://github.com/pigfox/solidity-pipeline) there
is exactly one Slither configuration in the estate, and every detector it
excludes is justified in one place:

→ **[lib/solidity-pipeline/docs/slither-exclusions.md](../lib/solidity-pipeline/docs/slither-exclusions.md)**

The two exclusions this repo used to own — `timestamp` and `incorrect-equality`,
firing on `PriceOracle`'s `updatedAt == 0` sentinel and its staleness window —
moved there, with the reasoning expanded. `incorrect-equality` is Medium
severity, so the shared document states plainly what is given up by switching it
off, rather than leaving it as a line in a config file with no reason attached.

The gate is still `fail_on: low`, and a full run over `src/` still reports **zero
results**. Everything not on the shared list remains enabled — in particular
state-affecting reentrancy, arbitrary-send, uninitialized-state,
unchecked-transfer, tx-origin, and the access-control detectors.

## Findings that were fixed rather than excluded

This part *is* repo-specific and stays. Two findings from the first Slither run
were resolved in code, not suppressed:

- **`reentrancy-no-eth` / `reentrancy-events` in `Redemption.requestRedemption`** —
  the request record and event now land *before* the external `token.burnFrom`
  call (strict checks-effects-interactions). The burn reverts the whole call on
  insufficient balance, so state can never diverge from the token.
- **`missing-inheritance`** — `IdentityRegistry`, `AssetRegistry` and `RWAToken`
  now explicitly inherit and `override` the interfaces (`IIdentityRegistry`,
  `IAssetRegistry`, `IRWAToken`) their siblings depend on, so the compiler
  enforces the surface the callers rely on.

`echidna_redemption_ledger_consistent` in `test/Properties.sol` is now the
standing guard on the first of those: it compares the recorded request against
what the harness asked for on every call, so a regression in that ordering fails
a property rather than waiting for the next static-analysis run.
