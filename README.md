# Bloxd Player Search Tasks

Dedicated public GitHub Actions runner repository for the private
[`bloxd-player-search`](https://github.com/imu31465/bloxd-player-search) source
repository. Pandra's CI and scheduled jobs remain in
[`scheduled-tasks`](https://github.com/imu31465/scheduled-tasks).

This repository contains workflow definitions only. The private application
source and player data are not copied here.

## Workflows

| Workflow | Trigger | Work |
|---|---|---|
| `census.yml` | Hourly at :47 UTC + manual | Four parallel ID-range workers; shared moving frontier |
| `sweep.yml` | Hourly at :13 UTC + manual | Five concurrent social-profile sweep workers |
| `enrich.yml` | Daily + manual + `ENRICH_NOW.json` commit | Profile enrichment drip / selected IDs; the tracked file gives a one-shot initial run after the first sweep finishes |
| `name-scan.yml` | Manual | Four-character name availability scan |
| `source-pr-validation.yml` | Manual + workflow-file update | Test merged source `main`/`runner` and merged Altare `main`, run PostgreSQL integration suites on disposable services, verify runner secrets with read-only Neon SELECTs, and lint workflow YAML |
| `production-availability.yml` | Every 15 minutes + manual + monitor-file update | Check the public gateway, all four Neon shards, and the login page; send Discord alert only when a check fails |

Each workflow checks out the private source repository's `runner` branch using
the read-only `DEPLOY_KEY` repository secret.

## Writer serialization

The census, sweep, and enrich workflows share the repository-wide
`player-search-writers` concurrency group. Only one of these database writers
may run at a time; the five sweep shards still run in parallel inside their
single sweep workflow. To fit the observed durations without building a queue,
the sweep runs hourly at minute :13 UTC and census runs hourly at minute :47 UTC.
The daily enrich job runs at 01:37 UTC, and its one-shot first run is started by
`ENRICH_NOW.json` after the initial sweep. A pending scheduled run may wait
behind the active writer; all three cursors are resumable so delayed runs can
catch up without overlapping database writes.

## Cutover lock

Production writers use the tracked root file `CUTOVER.json` as a fail-closed
switch. Every writer workflow reads it before starting any work:
- `enabled: false` or an invalid/missing file means **no writer jobs run**.
- `enabled: true` allows the scheduled/manual jobs to run.
- A commit changing only `CUTOVER.json` starts one initial census and sweep;
  enrich remains on its daily schedule to avoid an unnecessary extra social-API
  burst at activation. After the first sweep run finishes, commit a one-shot
  `ENRICH_NOW.json` file to start the initial enrichment run without waiting
  for the next daily cron.

This replaces the former `PLAYER_SEARCH_SHARD_CUTOVER` repository variable,
so the switch and every transition are version-controlled and reviewable.

**Keep `enabled: false` until all of the following are true:**

1. The shard-aware writer changes are merged into the private source
   repository's `runner` branch and their exact-head unit and PostgreSQL tests pass.
2. The source-to-shard migration has completed and its manifest reports
   `verified`, including all 64 bucket checks and exact source/target totals.
3. The Altare reader is deployed and authenticated search, profiles/history,
   lists, sorting, pagination, CSV, changes, and health checks pass against all
   four shards.
4. The current Bloxd session token has been derived and mint-validated.
5. The four repository secrets below point to the intended four distinct Neon
   projects, and the four-shard read/write integration tests pass.

To pause future writer starts, change `enabled` back to `false` in
`CUTOVER.json`. A run that has already started is not cancelled by changing
the switch; cancel an active run separately if an immediate stop is required.

The non-secret `SHARD_PROJECT_IDS` and 64-entry bucket map remain pinned in the
workflow files. Keep them synchronized with the four secret URLs and the
Altare/Neon environment; duplicate physical projects are rejected.

## Optional private Altare validation secret

The `source-pr-validation.yml` workflow also validates the private Altare reader/migration PR on public runners. It clones the Altare branch using a separate read-only Deploy Key stored in this repository as `ALTARE_VALIDATION_DEPLOY_KEY`. The validation job starts five disposable PostgreSQL 16 services (one source and four targets), runs the real migration CLI against synthetic records, and never uses Neon or production connection URLs.

This is separate from the source-repository `DEPLOY_KEY`; GitHub Deploy Keys cannot be reused across repositories. This validation key is not used by scheduled production workflows. The public workflow is configured to run after changes to its own workflow file and always validates the merged Altare `main` branch.

## Repository secrets

Open **Settings → Secrets and variables → Actions → Repository secrets** and
add four secrets:

| Name | Value |
|---|---|
| `DEPLOY_KEY` | Read-only SSH private key that can clone `imu31465/bloxd-player-search` |
| `DISCORD_WEBHOOK_URL` | Player Search notification webhook |
| `SHARD_01_DATABASE_URL` | Neon connection URL for `bloxd-search-shard-01` |
| `SHARD_DATABASE_URLS` | One-line JSON object containing all four Neon connection URLs |

Use the Neon Console **Connect** panel for each shard connection string. The
`SHARD_01_DATABASE_URL` value must exactly match the `shard-01` entry inside
`SHARD_DATABASE_URLS`. Do not paste connection strings or private keys into
chat, commits, workflow inputs, or logs.

The non-secret 64-entry bucket map is pinned directly in each workflow file. The four workflows use the same initial placement and must be updated together if the physical placement changes:

```json
["shard-01","shard-01","shard-01","shard-01","shard-01","shard-01","shard-01","shard-01","shard-01","shard-01","shard-01","shard-01","shard-01","shard-01","shard-01","shard-01","shard-02","shard-02","shard-02","shard-02","shard-02","shard-02","shard-02","shard-02","shard-02","shard-02","shard-02","shard-02","shard-02","shard-02","shard-02","shard-02","shard-03","shard-03","shard-03","shard-03","shard-03","shard-03","shard-03","shard-03","shard-03","shard-03","shard-03","shard-03","shard-03","shard-03","shard-03","shard-03","shard-04","shard-04","shard-04","shard-04","shard-04","shard-04","shard-04","shard-04","shard-04","shard-04","shard-04","shard-04","shard-04","shard-04","shard-04","shard-04"]
```

The URL object must have this shape (replace placeholders locally; never commit
real credentials):

```json
{"shard-01":"postgresql://...","shard-02":"postgresql://...","shard-03":"postgresql://...","shard-04":"postgresql://..."}
```

## Activation after cutover

After the checks above pass, set `enabled: true` in `CUTOVER.json` and commit
the change. That commit starts the initial census and sweep workflows. Confirm
both runs reach their expected completion states, then let the daily enrich schedule resume. The first enrich can be triggered by adding
`ENRICH_NOW.json` after the initial sweep has completed. Keep the old
single-database schedules disabled; never run old
and new writers concurrently. Keep the old database intact for rollback until
the new schedules have completed several clean cycles.

## Boundaries

- This repository owns Player Search scheduled tasks only.
- `scheduled-tasks` retains Pandra CI and Pandra-specific secrets.
- Player Search app source remains private.
- Neon credentials and deploy keys are repository secrets, never files.
- No data artifacts should be uploaded from census or sweep runs. The database
  is the source of truth for scan output and cursor state.


## Production cutover status — 2026-11-23

- The source-to-shard migration completed and the manifest is `verified`.
- Direct source/target SQL checks confirmed exact player, snapshot, and meta totals; all 64 bucket counts match the expected shard placement, snapshot orphan count is zero, and target sequences/indexes are valid.
- Altare PR #1 was merged to `main` at `caa16600106e3d7a4d851a8219d346eefacd251b` and deployed to Vercel Production. Before origin authentication was enabled, `/health` returned `200` with four healthy shards and `/login` returned `200`. After the security guard was enabled, direct Vercel origin requests correctly returned `403`; the Worker-routed health/login flow still needs external verification.
- Cloudflare Worker `bloxd-player-search-gateway` was updated to forward to `bloxd-player-search-altare.vercel.app`. Cloudflare reports the new version deployed at 100% traffic and the `ORIGIN_SECRET` binding remains present.
- Altare Production now uses `ALTARE=0` and a shared encrypted `ORIGIN_SECRET` with Cloudflare. A fresh Production redeploy is READY; direct requests to the Vercel `/health` and `/login` origins both return `403 Forbidden`. Cloudflare Worker secret version 5 is deployed at 100% traffic. The public Worker HTTP path still needs an external smoke check because the planner runtime cannot reach `workers.dev`.
- The tracked `CUTOVER.json` switch is `enabled: true` after the user completed browser acceptance and validation Runs #21/#22 passed. Initial census Run #24 succeeded with 30,000 new players; initial five-shard sweep Run #24 is still processing. Do not start old and new writers concurrently.
- The source project `little-dew-38530794` exhausted its November monthly storage allowance. The user approved removing all eight backup/test branches; the cleanup is verified and only the `production` branch remains (`ready`). The historical monthly allowance may remain exhausted until its December 1 reset. The original production branch and source data remain intact.

The validation workflow now checks merged source `main`, source `runner`, and Altare `main`, rather than obsolete topic branches. Run #14 (`45098137398`) succeeded on all four jobs. Its logs exposed a harmless shell-summary quoting defect, fixed in workflow commit `ebd25697767fe03b40dcfebf0658f2ee976bfd11`. The corrected run #15 (`45101519214`) succeeded on all four jobs and confirmed the exact branch heads and all required PostgreSQL integration tests:

- Source `main`: `ab3b94e25250d03ad95d5351744c22374a8dffe4`; 37 tests + PostgreSQL 4-shard writer integration passed.
- Source `runner`: `dd8d723392be429b88d38aff45b98f587fcb27c1`; 23 tests + PostgreSQL 4-shard writer integration passed.
- Altare `main`: `585c7fc7698ecb2b6c8f9ff5f5d8a1350161657c`; 41 tests passed, including the real PostgreSQL migration integration test (not skipped).
- Scheduled-runner secrets and read-only SELECT plus app-role grants passed for all four Neon targets.

### Latest verified production state

| Area | Verified state |
|---|---|
| Source PR #5 / #6 | Both merged; source main and runner production builds are READY |
| Altare PR #1 | Merged; main commit `caa16600106e3d7a4d851a8219d346eefacd251b` |
| Altare Vercel | Production redeploy `dpl_AR8RABHLATDd6cQsZe9Cin3xUxeb` READY |
| Altare origin guard | `ALTARE=0`; shared ORIGIN_SECRET configured in Vercel and Cloudflare; direct Vercel /health and /login return 403 |
| Cloudflare gateway | Routes to Altare; latest secret-backed version receives 100% traffic |
| Source live refresh | Old Vercel Production has `BLOXD_PROFILE_LIVE_REFRESH_ENABLED=0`; source main deployment is READY at `ab3b94e25250d03ad95d5351744c22374a8dffe4` |
| Neon source cleanup | Eight user-approved backup branches deleted; source production branch only, state ready |
| Scheduled workflows | `CUTOVER.json` enabled; initial census and sweep runs active |

**Completed 2026-11-23:** public gateway health reported all four shards, login returned HTTP 200, and the user verified authenticated search, a populated history profile, list sorting, page 2, changes feed, and CSV export. Production logs show HTTP 200 for the requested pages and CSV route. The source production branch remains intact as the rollback copy.


## Availability monitoring — 2026-11-23

The public Worker route was externally checked by run #16:
- `/health` returned `{"status":"ok","shards":4}`; the endpoint opens a database session to each configured shard.
- `/login` returned HTTP 200 with an HTML page.
- The same run passed the Altare PostgreSQL migration integration suite, source `main` writer tests, source `runner` writer tests, and all four Neon target connection/grant checks.

A 15-minute, read-only availability workflow repeats the public `/health` and `/login` checks. It sends Discord only on failure and does not write to Neon. The authenticated acceptance checks were completed on 2026-11-23; Run #21 and Run #22 also revalidated the production gateway and writer prerequisites. The current cutover switch is tracked in `CUTOVER.json`.

Latest run: https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45107111404
## Latest acceptance and performance verification — 2026-11-23

- The user confirmed authenticated browser acceptance for history, list sorting, page 2, changes feed, and CSV. Production runtime logs show each request returned HTTP 200.
- Altare search optimization PR #2 merged to `main` at `f9dc395e22c268f739297ff8c591f705c6a0a504` and was deployed to Vercel Production as READY. The search path now uses a UNION of current/former-name candidate IDs so PostgreSQL can use the existing trigram GIN index, and runs the four shard queries concurrently.
- Read-only `EXPLAIN (ANALYZE, BUFFERS)` comparisons on all four production shards confirmed the new SQL returned exactly the same ordered player IDs/names as the old SQL for current-name and former-name samples. The old query scanned roughly 718k player rows per shard and took 529–618 ms per shard; the new UNION plan used the trigram GIN index (6 ms warm on shard-03; 40–74 ms in colder-cache runs).
- Public-runner verification Run #21 succeeded: [run #21](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45178124440). It validated Altare `main` at the deployed SHA, passed all 42 Altare tests, ran the real PostgreSQL migration integration test without skipping, passed source `main` (37 tests + disposable four-shard writer integration), source `runner` (23 tests + disposable four-shard writer integration), verified all four Neon connection/app-role grants, checked the production gateway health/login, linted all workflows, and derived/mint-validated the current Bloxd token without logging its value.
- Source heads tested by Run #21: `main` `ab3b94e25250d03ad95d5351744c22374a8dffe4`; `runner` `dd8d723392be429b88d38aff45b98f587fcb27c1`. Altare deployed/tested head: `f9dc395e22c268f739297ff8c591f705c6a0a504`.
- Run #22 also passed after the tracked-gate conversion: [run #22](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45179000969). It validated the `CUTOVER.json` schema and all four updated writer workflow YAML files, reran the full Altare/PostgreSQL/source checks, and re-minted the current Bloxd token without logging its value.
- `CUTOVER.json` was enabled at commit `8a3597ec179e0e7a80601631907bd10b41e6d004` after the `enabled: false` dry-run workflows both completed successfully with every writer job skipped. The latest post-change validation [Run #25](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45182467944) passed all 7 jobs, including the shared writer-group gate checks and the `ENRICH_NOW.json` one-shot trigger. Census, sweep, and enrich now share one workflow-level concurrency group so they cannot write to Neon concurrently. Initial census run [#24](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45179485652) completed successfully: all 4 scan partitions finished with zero per-chunk probe errors, found 31,877 records, added 30,000 new players, and protected 1,877 enriched existing rows. Direct read-only checks after census finalization show 2,902,783 players and 241,919 snapshots, with 0 orphan snapshots; the next frontier cursor is 3,013,345 (2,000-ID overlap). Initial sweep run [#24](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45179485667) completed successfully across all five shards: 2,349 profile attempts, 2,345 successful fetches, 4 deleted/missing profiles (`gone`), 0 other errors, and 2 rank changes. All five worker cursors were saved. Direct read-only SQL after census+sweep shows 2,902,783 players, 243,062 snapshots, and 0 orphan snapshots across four shards. The first post-cutover enrich was then started by `ENRICH_NOW.json`: [run #45184140662](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45184140662); token mint validation passed and the drip refresh is running. Keep the original source database intact for rollback.


## Enrichment cursor recovery — 2026-11-24

The first post-cutover enrichment run was **not a full completion**, despite GitHub Actions showing a successful job conclusion. Run [#3 / 45184140662](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45184140662) ended after 1,490 seconds with the explicit log result:

`ok 400, changed 99, refreshed 179, snapshots 99, gone 14, err 0, skipped 4653, probe429 9345`, cursor `238032 -> 238032`, `ABORTED (fetch cap 400 reached)`.

The old implementation rewound the entire probe batch after a severe 429 storm and advanced to the end of a batch when the 400-call social-fetch budget was hit. That could repeatedly revisit the same range or defer unprocessed candidates until a full table wrap.

**Correction merged to the private source `runner` branch:**
- PR [#7](https://github.com/imu31465/bloxd-player-search/pull/7), merge commit `4747d199f20d903f3704e712e9838932c03722f8`.
- The cursor now resumes at the earliest unresolved ID, including probe 429s, unprocessed candidates after the fetch cap, transient fetch failures, and candidates left after a mint failure.
- The run summary and Discord embed report the number of pending IDs.
- Five new cursor regression tests cover earliest-pending selection, normal advancement, wrap-around, pending priority, and invalid pending IDs.
- Exact candidate head `e8b3b06c82c2d2796910538aeb93b3ca226c03af` passed public-runner validation [#36 / 45208940184](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45208940184): 28 unit/SQLite tests, the four-disposable-PostgreSQL writer integration, plus the full 8-job production validation workflow.

**Enrichment request rate was also reduced:** the scheduled workflow now probes at most 10,000 IDs per run with one probe worker, three retry rounds with 120-second initial wait, a 400-profile social-fetch cap, and a 50-minute job timeout. The daily schedule remains in place; it is not an hourly social-API poll.

Latest direct read-only Neon totals after census, sweep, and the first enrich run: **2,902,783 players, 243,160 snapshots, 0 orphan snapshots** across all four shards.

The corrected one-shot rerun [enrich Run #4 / 45210011080](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45210011080) finished with a green Actions job conclusion, but the source log explicitly says it **ABORTED at the 400-fetch cap**: 400 fetched, 367 changed (name 53 / colour 363 / cosmetics 363 / games 27), 369 refreshed, 367 snapshots, 17 gone, 0 fetch errors, 5,005 skipped, and 4,578 pending. The persisted cursor advanced from `238032` to `242336`; this is resumable progress, not full completion.

Direct read-only checks after Run #4: 2,902,783 players, 243,527 snapshots across four shards, and 0 orphan snapshots.

Keep the source production database intact for rollback.


## Five-way enrichment resumption — 2026-11-24

The 400-profile per-run limit was still too restrictive when applied to one global cursor: Run #4 spent 1,597 seconds probing 10,000 IDs and left 4,578 candidates for the next run. The scheduler now has a five-worker design, matching the already-proven five-worker social sweep:

- Player IDs are partitioned by `id % 5`; each worker reads and writes only its own partition.
- Each worker uses a separate control cursor, `census_enrich_cursor_0` through `census_enrich_cursor_4`. On the first sharded run, missing worker cursors inherit the previous global cursor `census_enrich_cursor` (`242336`), then advance independently.
- All five jobs pin the same private `runner` source SHA. Each has the existing 10,000-row probe limit, one probe thread, bounded 429 retries, 400 social-fetch cap, and 50-minute timeout. Maximum combined social fetch capacity is 2,000 profiles per scheduled run, subject to each partition's eligible candidates.
- Manual `force_ids` dispatch runs only on worker 0 to prevent duplicate forced fetches.

Implementation: private runner branch head `0c0b0d2e723c838926b0d929f54600755126635c`; task workflow commit `908279332b07072100f1c8943d955ece900bf366`. Public validation Run #40 (`45275348602`) and Run #41 (`45275942820`) both passed all 7 jobs. Run #41 validated private `runner` SHA `a2f3acd4770696a93f328e3ae2dbe743349722ac` (32 tests, PostgreSQL writer integration) and private `main` SHA `ab3b94e25250d03ad95d5351744c22374a8dffe4` (37 tests, PostgreSQL writer integration); Altare migration, four-shard GIN checks, secrets/Neon grants, live token, gateway, and workflow YAML all passed. Run #41 also validates the matrix-aware `step.if` correction. The live rollout is now the acceptance gate: all 5 worker logs and `census_enrich_cursor_0..4` must be checked against the four-shard database totals.


## Five-worker live attempt #1 — 2026-11-24

Task enrich Run #8 (`45276229332`) expanded all five partitions but failed before any profile fetch. Every worker cloned the partial private source and checked out the pinned SHA, then `git sparse-checkout set` needed to lazy-fetch a blob from the private promisor remote after the workflow had already deleted `~/.ssh/id_ed25519`. The log ended with `Permission denied (publickey)` / `could not fetch ... from promisor remote`. All five jobs failed at the clone step; no worker reached the DB update step.

Read-only reconciliation after Run #8: players `2,902,783`, snapshots `243,527`, orphan snapshots `0`; legacy cursor remains `242336`; none of `census_enrich_cursor_0..4` exists, confirming no shard wrote progress.

Fix: task workflow commit `5bc105cbbff239c1334d77dab4956daef20711fd` keeps the deploy key until after `sparse-checkout set` completes, then removes it. Validation Run #42 (`45276393947`) passed all 7 jobs: runner SHA `a2f3acd4770696a93f328e3ae2dbe743349722ac` (32 unit/SQLite tests + PostgreSQL writer integration), main SHA `ab3b94e25250d03ad95d5351744c22374a8dffe4` (37 unit/SQLite tests + PostgreSQL writer integration), Altare migration/four-shard GIN checks, live token, Neon grants, gateway and workflow YAML. The key-order fix is validated syntactically and will be exercised by the next live run.

The next one-shot retry uses the same five pinned disjoint partitions. Accept only after all five logs show the enrichment script ran and the five cursor keys plus four-shard integrity have been independently verified.


## Five-worker live attempt #2 — 2026-11-24 (bucket-map correction)

Task enrich Run #9 (`45276688505`) reached all five Drip workers after the private sparse-clone credential-order fix, but all five stopped before profile fetch with `ValueError: SHARD_BUCKET_MAP must be a JSON array of exactly 64 shard names`. Inspection of the workflow showed 63 entries: 16 each for shard-01/02/03 and only 15 for shard-04. This was a workflow configuration defect, not a Neon or Bloxd failure.

Correction in task workflow commit `536b7c6d0e017bbd22fcce6ab7626900c53b58dd`:
- Replaced the map using the proven 64-entry map from `sweep.yml` (16 buckets per each of four shards).
- Added a guard at the beginning of the Drip step to validate exactly 64 entries, 16 per shard, and complete project/URL maps before importing the application or opening a database connection.
- Run #43 (`45276953466`) validated the corrected workflow at that exact task HEAD and passed 7/7 jobs: private main/runner tests and PG writer checks, Altare migration and GIN checks, live token, Neon grants, gateway, and YAML.

Post-Run #9 read-only DB reconciliation: players `2,902,783`, snapshots `243,527`, orphan snapshots `0`; legacy cursor `242336`; no `census_enrich_cursor_0..4` keys. Therefore Run #9 did not update production rows or create shard cursors.

Next attempt must print `Storage map validated: 64 buckets, 16 per shard; all four shard configs present` in every worker log before the script starts. Only accept after all five fetch summaries and cursor keys are reconciled.


## Five-worker live attempt #3 — Run #10 in progress

Task enrich Run #10 (`45277205885`) started after the 64-bucket correction. Fail-closed cutover gate and common-source `prepare` both succeeded; the pinned private runner SHA is `a2f3acd4770696a93f328e3ae2dbe743349722ac`. All five matrix workers completed private sparse clone, Python setup, dependency installation, and live SP-token resolution; all five `Drip refresh partition i/5` steps are now running. Since each step passed the pre-DB storage-map guard before reaching its running state, the earlier 63-entry map error is not recurring.

At the latest check, no new per-worker cursor keys or snapshot count changes were yet visible in read-only Neon queries; this is an in-progress A-wave, not a completion. Wait for all five per-worker summaries before accepting, then reconcile cursor 0..4 and all four database totals.
