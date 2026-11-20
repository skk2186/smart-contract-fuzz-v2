# rwa-tokenization-demo

[![CI](https://github.com/pigfox/rwa-tokenization-demo/actions/workflows/ci.yml/badge.svg)](https://github.com/pigfox/rwa-tokenization-demo/actions/workflows/ci.yml)

Real-world asset tokenization with KYC-gated transfers on Base Sepolia.

A minimal, ERC-3643-inspired stack for fractionalizing a real-world asset as a
compliant ERC-20: every acquisition of tokens is gated on an on-chain KYC
whitelist. Minting requires a verified recipient; transfers require **both**
parties verified. The suite is hand rolled — the T-REX reference suite is
deliberately **not** vendored — so every line is in scope, 100% covered, and
checked by Slither and Echidna.

A live web walkthrough with client-signed wallet writes is served at
**https://pigfox.com/demos/rwa-tokenization**.

## Live on Base Sepolia

Chain id `84532`. All five contracts are source-verified on Basescan.

| Contract | Address |
|---|---|
| IdentityRegistry | [`0x11078533fb01015e52b1eaCD90d7BaE90B29f109`](https://sepolia.basescan.org/address/0x11078533fb01015e52b1eaCD90d7BaE90B29f109) |
| AssetRegistry | [`0x354718130d926f7cA148dc4935A7d946d4EA0c62`](https://sepolia.basescan.org/address/0x354718130d926f7cA148dc4935A7d946d4EA0c62) |
| PriceOracle | [`0xc787B126Dd60311eECf9501aFC3d7AdC2F348bBf`](https://sepolia.basescan.org/address/0xc787B126Dd60311eECf9501aFC3d7AdC2F348bBf) |
| RWAToken (ACME) | [`0xc01B935b7D62904E18C14f041E2611B582d1bf93`](https://sepolia.basescan.org/address/0xc01B935b7D62904E18C14f041E2611B582d1bf93) |
| Redemption | [`0xE41053aE6038E404dA764F96796288f9990Fe881`](https://sepolia.basescan.org/address/0xE41053aE6038E404dA764F96796288f9990Fe881) |

Deployed at block **44880606**. Machine-readable addresses and the seeded
narrative transactions live in [`deployments/base-sepolia.json`](deployments/base-sepolia.json).

## The compliance model

Five small contracts, one shared access-control base:

- **IdentityRegistry** — the KYC whitelist. Agents `registerIdentity` /
  `removeIdentity`; the token calls `isVerified` on every mint and transfer. It
  is bound one-shot to the token (`setToken`) so a holder cannot be
  de-verified while still holding tokens.
- **RWAToken** — a fractional ERC-20 (18 decimals). `mint` requires a verified
  recipient; `transfer`/`transferFrom` require both parties verified; `burnFrom`
  is restricted to the redeemer.
- **AssetRegistry** — registrar-only attestation of the off-chain assets that
  back the token (document hash, metadata URI, lifecycle status).
- **PriceOracle** — a mock push oracle exposing a price and a staleness stamp.
- **Redemption** — burns tokens against an active asset (strict CEI) and records
  a request an admin later settles.
- **Roles** — one `owner` (governance) + a set of `agents` (operations). The
  deployer is owner and first agent of every contract, so in this demo every
  privileged role is the one deployer address.

The full threat model, security invariants, and tooling results are in
[`SECURITY.md`](SECURITY.md).

## The seeded narrative

On deploy the stack is seeded so the demo page has real state to read: the
deployer and Investor A are whitelisted, twelve backing assets are registered,
an oracle price is pushed, and 10,000 ACME are minted to Investor A. Investor B
is deliberately left **un-whitelisted and keyless**. Four transactions then tell
the compliance story:

| Step | Tx | Result |
|---|---|---|
| Mint 10,000 ACME to verified Investor A | [`0x88f95a92…`](https://sepolia.basescan.org/tx/0x88f95a926e87133470961d28fb520b4397e1c307acfeed96b987dabd7c657e45) | success |
| Investor A → deployer, 1,000 ACME (both verified) | [`0xa412731e…`](https://sepolia.basescan.org/tx/0xa412731e07de33ae42c1374f2ee1b35980994398a4afe8ae557a354f074e646d) | success |
| **Investor A → Investor B, 500 ACME (B not verified)** | [`0x25ec03b4…`](https://sepolia.basescan.org/tx/0x25ec03b4a75f9044d32486898092135862fd02925e814e2f291cd948f97791bc) | **reverts on-chain — the compliance block** |
| Investor A redeems 2,000 ACME against asset 0 | [`0xf037dddf…`](https://sepolia.basescan.org/tx/0xf037dddfee855d94191e878a2f02d3ad3e329e772608f41cc7667c57ac678878) | success (burned) |

The reverting transfer is the showcase: an ordinary, correctly-formed ERC-20
transfer that the token itself refuses because the recipient is not KYC-verified.

## v1 deployment (retired 2026-07-26)

Everything above describes the deployment made on **2026-07-26**. An earlier one
ran from 2026-07-21 and is **retired**: its contracts are still on chain and keep
their own history, but nothing here reads them and none of the numbers above
belong to them. They are listed because the honest way to retire a deployment is
to say where it went, not to delete it.

| Contract | Retired address |
|---|---|
| IdentityRegistry | [`0x8FD97Ede1A00a35b2B74F0Ec84221C6791dd9b82`](https://sepolia.basescan.org/address/0x8FD97Ede1A00a35b2B74F0Ec84221C6791dd9b82) |
| AssetRegistry | [`0x4bB2186DCF0F41F98C1a8D302b35b7c90a44D024`](https://sepolia.basescan.org/address/0x4bB2186DCF0F41F98C1a8D302b35b7c90a44D024) |
| PriceOracle | [`0x5f307908D306987b0100b71b5de7B071D7b415Aa`](https://sepolia.basescan.org/address/0x5f307908D306987b0100b71b5de7B071D7b415Aa) |
| RWAToken (ACME) | [`0xf6d3fcecD5aa3AC8Dc77aF05FD4CC021171cCe32`](https://sepolia.basescan.org/address/0xf6d3fcecD5aa3AC8Dc77aF05FD4CC021171cCe32) |
| Redemption | [`0xcC74129807922abB787363D22955Ec1DebACa822`](https://sepolia.basescan.org/address/0xcC74129807922abB787363D22955Ec1DebACa822) |

Deployed at block 44520778. Its Investor A was
[`0x1aA17B67…`](https://sepolia.basescan.org/address/0x1aA17B67bE685BaBbe9DfE7abA44940b247756D6)
and its unverified Investor B
[`0xaF83046d…`](https://sepolia.basescan.org/address/0xaF83046d1B3FDDCF894E05Bc293E7f9dE26ee3ec).
The rotation that replaced every key and redeployed from scratch is recorded in
`pigfox2-repos/KEYS.md`.

## Cast one-liners

```bash
export RPC=https://sepolia.base.org
export TOKEN=0xc01B935b7D62904E18C14f041E2611B582d1bf93
export IDREG=0x11078533fb01015e52b1eaCD90d7BaE90B29f109
export ASSETS=0x354718130d926f7cA148dc4935A7d946d4EA0c62
export ORACLE=0xc787B126Dd60311eECf9501aFC3d7AdC2F348bBf
export REDEEM=0xE41053aE6038E404dA764F96796288f9990Fe881

# Token facts
cast call $TOKEN 'totalSupply()(uint256)'    --rpc-url $RPC
cast call $TOKEN 'balanceOf(address)(uint256)' 0xe2DA56b0f99bAfBC6c8E2c92f647F1F5ffBcc03E --rpc-url $RPC

# Is an address KYC-verified?
cast call $IDREG 'isVerified(address)(bool)' <addr> --rpc-url $RPC

# Asset registry + oracle
cast call $ASSETS 'assetCount()(uint256)'    --rpc-url $RPC
cast call $ASSETS 'getAsset(uint256)((bytes32,string,uint8,bool))' 0 --rpc-url $RPC
cast call $ORACLE 'latestPrice()(uint256,uint256)' --rpc-url $RPC

# Redemptions
cast call $REDEEM 'requestCount()(uint256)'  --rpc-url $RPC
cast call $REDEEM 'getRequest(uint256)((address,uint256,uint256,bool,bool))' 0 --rpc-url $RPC
```

## Testing

Verified by the
[**PIGFOX SOLIDITY PIPELINE v1**](https://github.com/pigfox/solidity-pipeline) —
the estate's single definition of green, consumed rather than copied. Every stage
runs on every push.

| Gate | Command | Result |
|---|---|---|
| Lint — step 1 | `lib/solidity-pipeline/scripts/lint-config-check.sh all`, then `forge lint` (bare) and `npx --yes solhint@6.2.3 -c lib/solidity-pipeline/.solhint.json --max-warnings 0 'src/**/*.sol'` | clean on `src/`; the copied `[lint]` block matches the canonical one |
| Unit + fuzz + invariant | `forge test` | **90 tests**, 7 suites; 6 invariants at 16,384 calls each, 0 reverts |
| Coverage | `lib/solidity-pipeline/scripts/coverage.sh` | **100%** lines / statements / branches / functions across all six `src/` files, no exclusions |
| Static analysis | `slither . --config-file lib/solidity-pipeline/slither.config.json --ignore-compile --fail-low` | 0 results at `fail_on: low` |
| Property fuzzing (Echidna) | `echidna . --contract Properties --config echidna.yaml` | **6/6** properties over 100,000 calls |
| Property fuzzing (Medusa) | `medusa fuzz --config medusa.json` | **6/6** properties over 100,000 calls |
| Doctrine gate | `lib/solidity-pipeline/scripts/no-chain-copy-gate.sh all` | direct-chain only; scan plus self-test |

Lint runs first because it is cheapest: no fuzzing, no coverage run and no chain,
so a style or natspec regression fails in seconds instead of after the fuzzers.
`forge lint` is invoked **bare** — passing it a path overrides the `ignore`
config. Every rule the estate turns off is argued in the pipeline's
[`docs/forge-lint-rules.md`](https://github.com/pigfox/solidity-pipeline/blob/main/docs/forge-lint-rules.md)
and [`docs/solhint-rules.md`](https://github.com/pigfox/solidity-pipeline/blob/main/docs/solhint-rules.md).

A single harness, `test/Properties.sol`, is driven by **all three** engines —
Foundry's invariant runner, Echidna and Medusa — so a property cannot hold under
one and quietly rot under another. Both fuzzers additionally assert the *number*
of properties they registered, so a predicate that silently stops being picked up
fails the build instead of reporting a smaller green run.

The six properties:

1. `echidna_supply_equals_sum_of_balances` — supply equals the sum of balances
2. `echidna_unverified_never_holds` — a never-verified address never holds a balance
3. `echidna_oracle_stamp_monotonic` — the oracle stamp never moves backwards
4. `echidna_supply_conserved` — everything minted, minus everything burned, is the supply
5. `echidna_redemption_ledger_consistent` — the redemption ledger is gapless and
   sequential, records exactly what was asked of it, and never settles twice
6. `echidna_redemption_requires_active_asset` — value is only ever destroyed
   against an asset the registrar has marked Active

Properties 4–6 and the harness's `Redemption` and `AssetRegistry` coverage are
new. The earlier harness fuzzed the token, the identity registry and the oracle,
and left the redemption ledger — the part of this system that destroys value —
with no invariant on it at all. Four `Actor` contracts now stand in for holders,
because `requestRedemption` records `msg.sender` and neither fuzzer has
cheatcodes; without them every redemption in a campaign would be the harness
redeeming from itself.

Slither's excluded detectors are justified in the shared
[pipeline exclusions doc](https://github.com/pigfox/solidity-pipeline/blob/main/docs/slither-exclusions.md);
findings this repo *fixed* rather than excluded are recorded in
[`docs/slither-exclusions.md`](docs/slither-exclusions.md).

## Setup

Secrets live in `.env` (gitignored) — copy [`.env.example`](.env.example) and
populate it, or keep the real file in `../.env`, one directory above this repo,
so it can never be committed. **Nothing in the build, test, or CI path reads
these values**; they are needed only to deploy and to seed. No key is ever placed
on a server or in CI.

```bash
git submodule update --init --recursive   # brings in lib/solidity-pipeline
forge build
forge test
lib/solidity-pipeline/scripts/coverage.sh   # 100% src/ gate
./scripts/deploy.sh            # deploy + seed to Base Sepolia (needs .env)
./scripts/seed-investor.sh     # the Investor-A-signed narrative txs
```

## Layout

```
src/                    Solidity contracts (Roles + the five system contracts)
  interfaces/           minimal interfaces the siblings depend on
test/                   unit + fuzz tests, Properties harness, Invariants runner
script/Deploy.s.sol     chain-id-guarded deploy + seed (deployer key)
scripts/                bash: deploy.sh, seed-investor.sh
lib/solidity-pipeline/  PIGFOX SOLIDITY PIPELINE v1 (submodule): gate scripts,
                        shared Slither config, shared property base
deployments/            committed record of addresses + narrative txs
docs/                   slither-exclusions.md (what was FIXED, not excluded)
echidna.yaml            Echidna config
medusa.json             Medusa config — same Properties.sol, second engine
```

## Licence

MIT. See [LICENSE](LICENSE).
