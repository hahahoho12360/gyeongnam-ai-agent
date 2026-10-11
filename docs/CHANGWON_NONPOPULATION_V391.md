# Changwon non-population repair v3.9.1

This workflow calls only the five non-population sources. Population metrics and source metadata are preserved. Firebase's current source-region-month state controls skipping, including the 1,112 combinations already committed by the failed v3.9 run; those are not recollected as targets.

Legal mapping checks the official 2026-10-10 code inventory. sggCd + five-digit umdCd resolves a legal ri to its parent eup/myeon. Name-only trade rows must match the official local or full legal name within the requested district. Unknown codes/names, missing/mismatched deal months and incomplete/repeated pages are failures, never no_data.

Before any collection writes, both trade sources are queried for all five districts for the earliest pending month. All ten checks must pass. The results are reused for that month; the same validations run for every subsequent group. Safe diagnostic fields exclude keys, URLs, free exception messages and private addresses. This preflight checks real API access in Actions, not in the offline unit tests.

Every run reads the current Firebase state and collects at most six remaining months per source. Transactions prevent repeated source writes and preserve other fields. Each run has a 250-minute work budget with 20 minutes reserved before starting another group. needs_continue dispatches the same immutable commit again; partial dispatches only when records were successfully applied. Automatic continuation is limited to 12 follow-ups to avoid endless error retries. A blocked preflight exits with an error before writing. Persistent errors and zero-progress partial runs require review.

Indexes use one atomic monthly batch (at most 409 writes) with a completion checkpoint. Dirty months and their next-month/year dependents invalidate checkpoints before recomputation. Missing checkpoints trigger a first full verification/recompute. Population repair and non-population fill share the same writer concurrency group.

## Starting and interpreting the run

The initial authorized run is triggered only by updating docs/NONPOPULATION_V391_RUN.txt on main. Ordinary code changes do not trigger another collection. Manual runs: Actions → Changwon non-population audit and repair v3.9.1 final → Run workflow → main → mode fill; leave continuation_attempt at 0.

Download preflight.json, before.json, after.json and result.json from Artifacts. Only status complete means no unqueried items remain and the indexing loop finished. needs_continue/partial are unfinished, even when Actions is green. conflict/legacy_unverified remain separate manual-review conditions. Current building/K-APT/commerce snapshots do not imply 48 months of historical snapshots. An endpoint may return transactions in previously completed areas while pending areas have none; district queries are required to establish this, but completed records are not overwritten.
