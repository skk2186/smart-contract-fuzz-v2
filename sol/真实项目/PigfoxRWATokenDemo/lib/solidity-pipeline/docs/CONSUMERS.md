# The consumer list, and the limits of guarding it

`consumers.json` at the repo root is the canonical list of repos on the pipeline.
`scripts/consumers-check.sh` runs in CI and fails the build if `README.md`'s
"Repos on the pipeline" table disagrees with it, in either direction.

## Why this exists

The table was hand-maintained prose in two places, and both went stale. It listed
**four** repos when six were on the pipeline — `interest-rate-model` and
`oracle-health-explorer` had adopted the pipeline and were never added — and
`ADOPTING.md` repeated a matching wrong count.

Nothing failed, because nothing checked. That is the whole problem: a stale
enumeration reads as a decision. "These are the repos on the pipeline" carries the
same authority whether or not it is true, and a reader has no way to tell the
difference. It is the same defect class as a coverage exclusion that matches no
row — which this pipeline already fails the build for, and for the same reason.

## What the guard catches

- A repo in `consumers.json` with no row in the README table.
- A row in the README table with no entry in `consumers.json`.
- A description that has drifted between the two.
- An empty list on either side — it refuses to pass vacuously.

It self-tests before it is trusted, planting exactly the defect that shipped (a
consumer missing from the README) and refusing to pass unless it catches it. A
checker that has silently stopped matching reports the same green as a correct
tree; that lesson is already written into `no-chain-copy-gate.sh` and
`property-count.sh`, and it applies here too.

## What the guard does NOT catch, and why

**It cannot discover a repo that adopted the pipeline and was never added to
`consumers.json`.** That is precisely the rot that happened, so the gap is worth
stating plainly rather than leaving a reader to assume the guard is complete.

Catching it means answering "which repos in the org call this workflow?", which
this repo cannot answer from its own tree. It would need to enumerate the GitHub
organisation and read each repo's `.github/workflows/ci.yml` — network access, a
token with cross-repo read scope, and a new failure mode in which a GitHub outage
or a rate limit turns an unchanged tree red. For a gate whose entire value is that
green means the same thing every time, that trade is bad: a deterministic offline
check that covers most of the surface beats a flaky complete one that people learn
to re-run until it passes.

So the residual gap is closed by procedure, not by code, and the procedure is one
line in `ADOPTING.md`: **a repo adds itself to `consumers.json` in the same commit
that adopts the pipeline.** If that step is missed, the guard stays green and the
list stays short — the same as today, except that the list is now in one place
instead of scattered through prose, and every other way it could rot is covered.

If cross-repo discovery ever becomes worth the flakiness, the right home for it is
a scheduled job that opens an issue, not a required check on every push.
