// SPDX-License-Identifier: MIT
pragma solidity >=0.8.0;

/// @title PigfoxProperties — the shared property-harness contract for the estate.
/// @notice Every pigfox contract repo has exactly one `test/Properties.sol`
///         holding a contract `Properties is PigfoxProperties`. Foundry, Echidna
///         and Medusa all drive THAT contract, so an invariant can never hold in
///         one engine and quietly rot in another.
///
/// @dev    WHY THIS BASE EXISTS AT ALL.
///         A property harness has a failure mode worse than a failing property:
///         a property that stops being *registered*. A rename, a stale
///         `crytic-export/`, artifacts left behind by `forge coverage`, a
///         `testPrefixes` mismatch — any of these makes a fuzzer walk a smaller
///         property set and report a green run. It has happened in this estate:
///         a stale artifact once shrank a five-property set to four and the job
///         passed. Green on four is not green.
///
///         So the count is declared in Solidity, and three independent things
///         must agree with it before a build passes:
///
///           1. `pigfoxPropertyCount()` — this declaration, in the source.
///           2. The static count of `function echidna_` declarations in
///              `test/Properties.sol`, checked by
///              `scripts/property-count.sh --source`.
///           3. What Echidna and Medusa each actually REGISTERED at runtime,
///              checked by `scripts/property-count.sh --engine`.
///
///         Two of those can be wrong together only if someone edits the source
///         and the declaration in the same breath, which is a deliberate act with
///         a diff attached. That is the point.
///
/// @dev    NO DEPENDENCIES, DELIBERATELY. This file imports nothing — not
///         forge-std, not OpenZeppelin. It is vendored into consuming repos as a
///         git submodule under `lib/`, and a base contract that dragged in a
///         second copy of forge-std would create exactly the duplicate-artifact
///         confusion the count guard exists to catch.
///
/// @dev    The pragma is a floating `>=0.8.0` rather than a pin. Consuming repos
///         pin their own exact `solc` in `foundry.toml`; that pin is the control.
///         Pinning here too would mean this file blocks a repo from moving
///         compiler versions independently, for no safety gain.
abstract contract PigfoxProperties {
    /// @notice How many `echidna_*` predicates this harness declares.
    /// @dev    Override with a literal, not a computed expression. The whole
    ///         value of this number is that it is an independent statement of
    ///         intent — deriving it from anything the harness already knows
    ///         would make it agree with a broken harness automatically.
    ///
    ///         `pure` and prefixed `pigfox`, not `echidna_`, so no fuzzer ever
    ///         mistakes the declaration for one of the properties it counts.
    /// @return The number of `echidna_*` predicates in this contract.
    function pigfoxPropertyCount() public pure virtual returns (uint256);

    /// @notice A one-line statement of what this harness is proving.
    /// @dev    Read into the CI log by the pipeline so a run says what it
    ///         covered rather than only how many things it covered. Override it;
    ///         the default is deliberately useless so an unoverridden harness
    ///         reads as unfinished rather than as fine.
    /// @return A short human-readable description of the harness.
    function pigfoxHarnessDescription() public pure virtual returns (string memory) {
        return "UNDESCRIBED HARNESS";
    }
}
