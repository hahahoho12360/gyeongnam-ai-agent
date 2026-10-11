# One-month original API repair v3.7.2

Workflow: `Changwon population one-month verified repair v3.7.2`.
Initial authorized run: 2024-08. Probe code: 4812725028 (내서읍 삼계리).

The new workflow runs once when its workflow file is pushed, and can subsequently
be dispatched manually with a benchmarked month. It shares the existing writer
concurrency group; it does not cancel another population repair.

1. Probe each original API for one month and a three-month range. Record HTTP
   status, provider result codes, successful pages, rows, elapsed time and safely
   classified errors. Compare the target month's single/range rows when both work.
2. If all three single-month probes work, collect only the selected month, using
   two workers and successful original-response checkpoints. A failed range alone
   does not prohibit using successful single-month queries.
3. Stop before new requests/retries when the deadline is near, or after six
   consecutive failed request attempts. Requests have 5-second connect and
   20-second read timeouts; at most one retry. A 70-minute process timeout and
   80-minute job timeout provide independent bounds.
4. Validate all region/ri responses and official city/five-district totals before
   the one-month Firestore batch. Read back every population patch and check all
   official totals after the write. Preserve other sources' fields.
5. Artifact `one_month_status.json` distinguishes `complete`, `already_verified`,
   `paused`, and `blocked`. `complete` requires actual read-back equality and
   `applied_this_run: 1`. Already verified means no new repair was needed.

Samgye is a legal ri: its response is aggregated into parent Naeseo-eup in the
204-region public dataset; it does not become a 205th overview region.
Derived metrics and indexes are deliberately marked for subsequent recomputation.
Paused runs preserve successful captures, and reruns verify existing totals first.
Raw official aggregate API captures are retained in access-controlled Artifacts;
credentials and request URLs containing credentials are never written to reports.
