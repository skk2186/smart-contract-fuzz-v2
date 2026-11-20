# forge lint — every exclusion, and why

`config/lint.toml` holds the canonical `[lint]` block for the estate. Each repo
copies it verbatim into its `foundry.toml`, and `scripts/lint-config-check.sh`
fails CI if a copy drifts. A rule turned off that is not written down here does
not exist — the same discipline as
[slither-exclusions.md](slither-exclusions.md) and [solhint-rules.md](solhint-rules.md).

## Why this one is copied when the other two are not

Slither takes `--config-file` and Solhint takes `-c`, so both are consumed
straight from this submodule and exist in exactly one place. **`forge lint` has
neither.** It reads the `[lint]` table of the `foundry.toml` belonging to the tree
being linted, and there is no override.

So the block is copied, like `config/echidna.yaml` and `config/medusa.json` — and
like those, the copy is checked rather than trusted. `lint-config-check.sh`
compares each repo's `exclude_lints` against the canonical set exactly, and
requires both canonical `ignore` entries to be present. It self-tests before it is
believed, including the case that matters: an **undocumented extra exclusion**
must be caught.

## Two traps worth knowing

**Invoke it bare.** `forge lint src/` OVERRIDES the `ignore` setting — this is
documented in `forge lint --help` ("Overrides the `ignore` project config"), and
it means the obvious-looking invocation lints the generated verifiers this config
exists to skip. The gate runs `forge lint` with no path argument.

**The pattern needs the `/*.sol` suffix.** `ignore = ["test/**"]` does **not**
match, and fails silently: the findings stay, while the config reads as if it had
scoped them away. `ignore = ["test/**/*.sol"]` works. This was measured, not
assumed — the first version of this block left 14 findings in place while looking
correct.

## Scope

`src/` only, mirroring `filter_paths` in `slither.config.json` and the `src/`-only
scope of `.solhint.json`. Beyond "test code is not the artifact under test", a
naming linter and Foundry disagree *by construction* in `test/`: Foundry discovers
tests by the `test` / `testFuzz` / `invariant_` prefixes, and pipeline law requires
`echidna_*` predicates. `mixed-case-function` and `mixed-case-variable` can only be
satisfied there by breaking test discovery, so scoping removes them without a
single suppression — and without renaming anything, which standing law forbids.

## Rule exclusions

| Rule | Reason |
| --- | --- |
| `screaming-snake-case-const` | Fires on `uint8 public constant decimals = 18` in `RWAToken` and `KYCToken`. **ERC-20 fixes `decimals` in lower case**; renaming it changes the public getter and breaks every ERC-20 consumer. Identical to the argument already recorded for Slither's `naming-convention` and Solhint's `const-name-snakecase`. |
| `screaming-snake-case-immutable` | Wants `SCREAMING_SNAKE_CASE` for immutables, which would rename the registry handles — `token`, `identityRegistry`, `assetRegistry`. Those read most naturally in mixedCase and mirror the ERC-3643 naming the RWA demo follows deliberately. Same code, same reason, as Solhint's `immutable-vars-naming`. |
| `unwrapped-modifier-logic` | Suggests moving a modifier's body into an internal function to reduce code size. `Roles.onlyOwner` and `Roles.onlyAgent` are two lines each; the largest contract in the estate (`EscrowUpgradeable`) is **7,299 bytes against a 24,576 limit**, so there is no code-size problem to solve. The indirection would hide the access check from the site that applies it — a real readability cost for a saving nobody needs. |

## What is NOT excluded

Everything else `forge lint` ships runs at full strength on `src/`, including
`incorrect-shift`, `divide-before-multiply`, `unsafe-typecast`,
`erc20-unchecked-transfer`, `unchecked-call`, and the whole high/medium tier. A
finding there is a finding.

`unsafe-typecast`, `erc20-unchecked-transfer` and `unsafe-cheatcode` currently fire
only in `test/`, which the scope removes. They are **not** excluded — if one ever
appears in `src/`, it fails the build, which is the intended behaviour.

## Adding an exclusion

1. Add a row above with a reason that would convince a reviewer who did not write
   the code. "It is noisy" is not a reason.
2. Add the rule to `config/lint.toml`.
3. Copy the updated block into every consuming repo — `lint-config-check.sh` will
   fail any you miss, which is the point.

Per-line suppressions are not used. `// forge-lint: disable-next-line` scattered
through the source is the same "silently configured away" pattern
`slither-exclusions.md` forbids: invisible from the config, invisible from CI
output, and it outlives the reason for it.
