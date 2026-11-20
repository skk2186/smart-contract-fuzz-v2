# Security

This is a demonstration project on Base Sepolia (a testnet). It holds no real
value and is not audited for production use. That said, the contracts are
written and verified to production standards, and this document is the reviewer's
map of what is guaranteed, how it is enforced, and where the trust boundaries
sit.

## What the system does

A minimal, ERC-3643-inspired real-world-asset (RWA) tokenization stack, hand
rolled (the T-REX suite is deliberately **not** vendored) so every line is in
scope:

- **IdentityRegistry** — the KYC whitelist. Agents add and remove verified
  identities; the token consults it on every mint and transfer.
- **RWAToken** — a fractional ERC-20 whose compliance hooks gate every
  acquisition of tokens on KYC verification.
- **AssetRegistry** — registrar-only attestation of the off-chain assets that
  back the token (document hash, metadata URI, lifecycle status).
- **PriceOracle** — a mock push oracle exposing a price and a staleness stamp.
- **Redemption** — burns tokens against a registered asset and records a
  request an admin later settles.
- **Roles** — the shared owner/agent access-control base every contract extends.

## Security invariants

These are the properties the contracts are designed to guarantee. Each is
enforced in code, exercised by unit tests, and — for the core three — checked by
both Foundry's invariant runner and Echidna.

1. **A non-verified address can never hold a non-zero token balance.**
   Enforced on two fronts: (a) *acquisition* is gated — `mint` requires the
   recipient to be verified, and `_transfer` requires **both** parties verified;
   (b) *de-verification* is gated — `IdentityRegistry.removeIdentity` reverts if
   the identity still holds tokens (the registry is bound to the token one-shot
   via `setToken`, and the binding cannot later be disabled). Together these
   close both the "acquire while unverified" and the "become unverified while
   holding" escape paths.
   *(Echidna `echidna_unverified_never_holds`, Foundry `invariant_UnverifiedNeverHolds`.)*

2. **`totalSupply` always equals the sum of all balances.**
   Only `mint` (increments supply and one balance) and `burnFrom` (decrements
   both) change supply; `_transfer` moves value between balances without
   touching supply.
   *(Echidna `echidna_supply_equals_sum_of_balances`, Foundry `invariant_SupplyEqualsSumOfBalances`.)*

3. **Redemption burns exactly the requested amount, from the caller only.**
   `requestRedemption` passes `msg.sender` as the holder to `burnFrom`, so a
   caller can only ever redeem their own holding. `burnFrom` is restricted to
   the single configured `redeemer` (the Redemption contract).

4. **The oracle staleness stamp is monotonic.**
   `updatedAt` is only ever assigned `block.timestamp`, which never moves
   backwards between transactions.
   *(Echidna `echidna_oracle_stamp_monotonic`, Foundry `invariant_OracleStampMonotonic`.)*

## Access control

A single `Roles` base gives every contract one `owner` (governance) and a set of
`agents` (operational actors). The deployer is set as owner **and** the first
agent in each constructor, so in this demo every privileged role resolves to the
one deployer address. `onlyOwner` guards governance (ownership transfer, agent
management, and the one-shot wiring setters); `onlyAgent` guards operations
(identity registration, asset registration, minting, price pushes, redemption
settlement). Ownership transfer does **not** auto-grant the new owner an agent
role — that is a separate, explicit `setAgent` call.

## Trust boundaries

- **Agents are trusted.** A malicious agent can mint arbitrarily, whitelist
  arbitrary identities, and push arbitrary prices. This is inherent to a
  permissioned RWA design; the guarantee is that a **non-agent cannot**.
- **The oracle is a mock.** It is a push oracle with no source verification; do
  not treat its price as trustworthy market data.
- **Redemption settlement is an attestation.** `settleRedemption` records that
  an off-chain payout happened; it moves no on-chain value.
- **Off-chain data is attacker-authored.** Asset URIs and document hashes are
  free-form inputs. Any consumer (including the demo web page) must treat them
  as untrusted — render as text, never as markup, and never dereference a URI
  as code.

## Tooling and how to reproduce it

| Gate | Command | Result |
|---|---|---|
| Unit + fuzz + invariant tests | `forge test` | 83 tests pass; 3 invariants at 16,384 calls each, 0 reverts |
| Coverage | `./scripts/coverage.sh` | 100% of lines, statements, branches, and functions across all six `src/` files |
| Static analysis | `slither . --config-file slither.config.json` | 0 results at `fail_on: low` (exclusions triaged in [`docs/slither-exclusions.md`](docs/slither-exclusions.md)) |
| Property fuzzing | `echidna . --contract Properties --config echidna.yaml` | all 3 properties passing over 100,000 calls |

### Echidna results

The `test/Properties.sol` harness owns every privileged role and drives token
state exclusively through wrapped actions, so the fuzzer's arbitrary `msg.sender`
never needs the agent role. A never-verified `PHANTOM` address is included in the
account set: no action can ever give it a balance, which is invariant #1 made
concrete. A run of 100,000 calls reports:

```
echidna_supply_equals_sum_of_balances: passing
echidna_oracle_stamp_monotonic:        passing
echidna_unverified_never_holds:        passing
```

### Slither triage

A full Slither run over `src/` reports zero findings at `fail_on: low`. Two
findings from the first pass — a checks-effects-interactions ordering in
`requestRedemption` and missing interface inheritance — were **fixed in code**
rather than suppressed. The four remaining excluded detectors
(`naming-convention`, `solc-version`, `timestamp`, `incorrect-equality`) are each
individually justified in [`docs/slither-exclusions.md`](docs/slither-exclusions.md);
everything else, including all reentrancy and arbitrary-send detectors, stays
enabled.

## Keys and secrets

No private key is ever committed, placed on a server, or printed. Secrets live
only in the developer's local `.env` (and its `../.env` copy one directory above
the repo); nothing in the build, test, or CI path reads them. CI runs on a clean
checkout with no secrets — only deployment, done manually from a laptop, needs a
key. See the README for the full setup contract.

## Reporting

This is a testnet demo with no bug-bounty program. If you spot something
interesting, open an issue on the repository.
