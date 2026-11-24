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


## Five-worker live Run #10 — 2026-11-24 (verified)

[Run #10 / 45277205885](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45277205885) completed successfully at the Actions level; all five worker jobs and both setup jobs succeeded. All five logs explicitly show the 64-bucket configuration guard passed and the enrichment process ran.

Per-worker results:

| Worker | fetched/ok | changed + snapshots | gone | errors | pending | cursor |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 400 | 391 | 3 | 0 | 8,368 | 250,500 |
| 1 | 400 | 400 | 1 | 0 | 9,599 | 244,341 |
| 2 | 400 | 400 | 4 | 0 | 9,596 | 244,357 |
| 3 | 400 | 400 | 2 | 0 | 9,598 | 244,348 |
| 4 | 400 | 400 | 2 | 0 | 9,598 | 244,349 |

Combined: 2,000 social fetches, 1,991 changed profiles/snapshots, 12 gone, 0 errors. Each worker reached its intentional `--fetch-cap 400`, so the script summary says `ABORTED (fetch cap 400 reached)` while the GitHub job concludes success. This is bounded, resumable progress, not a completed full-corpus enrichment.

Independent read-only Neon reconciliation after Run #10:
- Players: `2,925,497` total.
- Snapshots: `246,149` total.
- Orphan snapshots: `0`.
- Per-shard players: shard01 `731,408`; shard02 `731,311`; shard03 `731,429`; shard04 `731,349`.
- Per-shard snapshots: shard01 `61,504`; shard02 `61,533`; shard03 `61,553`; shard04 `61,559`.
- Control DB cursor keys: `census_enrich_cursor_0=250500`, `_1=244341`, `_2=244357`, `_3=244348`, `_4=244349`; legacy cursor remains `242336`.

The count increase since the earlier baseline is also reconciled with independent scheduled jobs: census Run #9 added 22,714 new players across its three successfully published scan partitions (scan 0 rejected six unresolved probes and did not publish partial progress); social sweep Run #9 recorded 631 snapshots across its five workers; enrichment Run #10 recorded 1,991 snapshots. Total snapshot delta = 631 + 1,991 = 2,622, matching `243,527 → 246,149`. No orphan rows were created.

Next: continue the bounded five-worker catch-up from the five stored cursors. Keep the 400-per-worker guard until the backlog is drained; do not mark the corpus fully enriched just because Actions is green.

## Five-worker live Run #11 — 2026-11-24 (verified)

[Task Run #11 / 45310792967](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45310792967) completed with conclusion success. The fail-closed cutover gate and common-source preparation succeeded, and all five drip matrix jobs completed. Each worker cloned the pinned private source SHA a2f3acd4770696a93f328e3ae2dbe743349722ac, derived a live 60-character Bloxd session token and passed mint validation, passed the pre-DB guard confirming exactly 64 buckets (16 per shard) and all four shard configurations, and completed 400 profile fetches with 0 fetch errors.

Per-worker results (cursor values are the persisted end cursors):

| Worker | fetched/ok | changed + snapshots | gone | errors | skipped | pending | cursor |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 400 | 400 | 1 | 0 | 113 | 9,486 | 253,070 |
| 1 | 400 | 400 | 1 | 0 | 0 | 9,599 | 246,346 |
| 2 | 400 | 400 | 0 | 0 | 0 | 9,600 | 246,357 |
| 3 | 400 | 400 | 1 | 0 | 0 | 9,599 | 246,353 |
| 4 | 400 | 400 | 2 | 0 | 0 | 9,598 | 246,359 |

Combined: 2,000 profile fetches, 2,000 changed profiles/snapshots, 5 gone, 0 fetch errors. All five workers reached the intentional 400-fetch cap, so the script logs say ABORTED (fetch cap 400 reached) despite successful GitHub job conclusions. This is bounded, resumable progress and **not** proof that all profiles are enriched. Worker0's skipped count is retained in the run record; its persisted cursor moved from 250500 to 253070.

Independent read-only Neon reconciliation after Run #11:

| Shard | Players | Snapshots | Orphan snapshots |
|---|---:|---:|---:|
| shard-01 | 731,408 | 62,011 | 0 |
| shard-02 | 731,311 | 62,030 | 0 |
| shard-03 | 731,429 | 62,048 | 0 |
| shard-04 | 731,349 | 62,060 | 0 |
| **Total** | **2,925,497** | **248,149** | **0** |

The five persisted control cursors are census_enrich_cursor_0=253070, _1=246346, _2=246357, _3=246353, and _4=246359; the legacy cursor remains 242336. Snapshot totals reconcile exactly from Run #10's 246,149 to 248,149 (+2,000). Player totals are unchanged. No orphan snapshots were created.

Continue the five-worker catch-up from these saved cursors. Keep the 400-per-worker cap and do not mark full-corpus enrichment complete until unresolved work is demonstrably drained and separately reconciled.

## Full-pass enrichment continuation — 2026-11-24

The one-shot trigger now has a resumable full-pass controller, so catch-up does not require someone to manually push ENRICH_NOW.json after every bounded batch.

- Run #12 (45324488471) was launched from the five persisted cursors after Run #11. Its five workers retain the current conservative limits: one probe worker, 10,000 rows per partition window, 400 social fetches per worker, and 0.7-second spacing.
- .github/workflows/enrich-continuation.yml listens for completion of the enrich workflow. It downloads the completed run logs, parses each active worker's summary and cursor, and updates ENRICH_PROGRESS.json.
- A worker is marked complete after its cursor wraps from its saved high-water mark to a lower ID, proving it reached the end of its remaining ID range. Completed workers are skipped in later runs. The controller dispatches another bounded enrich run for unfinished workers.
- The chain pauses instead of immediately retrying when logs are missing or ambiguous, a worker reports HTTP 429, a fetch error, or an abort other than the intentional 400-fetch cap. The daily schedule remains a safe retry path. Manual force_ids runs are not auto-chained.
- When all five worker cursors have completed their first pass, ENRICH_PROGRESS.json becomes status completed; the gate then skips normal scheduled enrichment workers. A green Actions conclusion alone is never treated as full-pass completion.
- ENRICH_PROGRESS.json starts from the five saved cursors after Run #11 and tracks completed shards, last run, latest worker summaries, and pause reasons.
- Public-runner validation Run #46 / 45325982606 passed all seven jobs against task HEAD a58470252b0eecc84d01c4636a2dff551778d5b0, including every workflow YAML file, both source branch test/PostgreSQL suites, Altare migration/index tests, live token mint validation, four-shard Neon read/grant checks, and production gateway checks.

Read-only profiling found 2,683,506 player rows currently store an empty JSON object in cosmetics (shard counts 670,934 / 670,850 / 670,905 / 670,817). The current A-gate treats an empty cosmetics object as not yet enriched, so this is an upper-bound indication of the work the cursor may encounter, not an exact remaining-fetch count: the probe, cooldown, name-match and other skip rules still filter candidates. Keep the per-runner 400 cap until observed logs justify a change.

## Five-worker live Run #12 — 2026-11-24 (verified)

[Task enrich Run #12 / 45324488471](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45324488471) completed successfully. All five workers passed live SP-token mint validation and the pre-DB storage-map guard (64 buckets, 16 per shard), then fetched 400 profiles each.

| Worker | fetched | changed | snapshots | gone | errors | pending | cursor |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 400 | 400 | 400 | 2 | 0 | 9,598 | 253070 → 255080 |
| 1 | 400 | 400 | 400 | 2 | 0 | 9,598 | 246346 → 248361 |
| 2 | 400 | 400 | 400 | 4 | 0 | 9,596 | 246357 → 248377 |
| 3 | 400 | 400 | 400 | 1 | 0 | 9,599 | 246353 → 248358 |
| 4 | 400 | 400 | 400 | 1 | 0 | 9,599 | 246359 → 248364 |

Combined: 2,000 successful profile fetches, 2,000 changed profiles/snapshots, 10 gone, 0 fetch errors. All five reached the intentional 400-fetch cap, so their summaries say ABORTED (fetch cap 400 reached). This is resumable progress, not full-corpus completion.

Independent post-run read-only reconciliation across all four Neon shards:
- Players: 2,925,497 total (unchanged).
- Snapshots: 250,149 total (up exactly 2,000 from Run #11).
- Orphan snapshots: 0 on all four shards.
- Per-shard players/snapshots: shard-01 731,408 / 62,507; shard-02 731,311 / 62,536; shard-03 731,429 / 62,549; shard-04 731,349 / 62,557.
- Worker cursors persisted as 255080 / 248361 / 248377 / 248358 / 248364; legacy cursor remains 242336.
- Empty cosmetics JSON rows are now 2,681,512 (down from 2,683,506 at Run #11); this is an upper-bound candidate indicator, not an exact remaining-fetch count.

## Continuation controller repair — 2026-11-24

The first controller attempt after Run #12 paused safely with missing-or-ambiguous-summary-0 because the run-log ZIP parsing did not identify the worker logs. No data was rolled back: Run #12 had already saved all five cursors and its database writes were independently reconciled. The controller was rebuilt to query the workflow-run jobs list, map the exact drip (0..4) job IDs, and download each job's plain-text log directly. Progress state was restored with all five verified Run #12 summaries and end cursors; the status is running, with no completed partitions yet.

The rebuilt controller at task HEAD e3c95189a4457e6abfd3303418fb8e907ae20510 passed public validation [Run #49 / 45328454114](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45328454114), all seven jobs including workflow YAML parsing and the source/Altare PostgreSQL integration suites. The direct job-log parser will be live-verified by the next chained run; the chain must pause again on missing summaries, HTTP 429s, fetch errors, or unexpected aborts.
## Five-worker live Run #14 — 2026-11-24

[Enrich continuation Run #14 / 45331636181](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45331636181) completed successfully. The run was launched by the controller after Run #13. All five workers passed live SP mint validation and the 64-bucket/four-shard guard.

| Worker | fetched | changed | snapshots | gone | errors | pending | cursor |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 400 | 400 | 400 | 1 | 0 | 9,599 | 257090 → 259095 |
| 1 | 400 | 400 | 400 | 2 | 0 | 9,598 | 250386 → 252396 |
| 2 | 400 | 400 | 400 | 1 | 0 | 9,599 | 250387 → 252392 |
| 3 | 400 | 400 | 400 | 0 | 0 | 9,600 | 250358 → 252368 |
| 4 | 400 | 400 | 400 | 0 | 0 | 9,600 | 250369 → 252369 |

Combined: 2,000 fetches, 2,000 changed profiles/snapshots, 4 gone, and 0 fetch errors. Each worker reached the intentional 400-fetch cap; this is another bounded batch, not full-pass completion.

Post-run read-only Neon reconciliation across all four shards: 2,925,497 players, 254,149 snapshots, 0 orphan snapshots, and 2,677,526 rows with empty cosmetics JSON. Max player IDs by shard are 3,053,327 / 3,053,343 / 3,053,345 / 3,053,311. Persisted cursors: worker0 259095, worker1 252396, worker2 252392, worker3 252368, worker4 252369 (legacy 242336).

## Continuation trigger matching repair — 2026-11-24

Run #14 was started with workflow_dispatch and run-name 'Enrich continuation'. The controller had been filtered by static workflow name 'enrich', so GitHub did not trigger it again after Run #14. The controller was changed to listen for all workflow_run completions and filter its job by the stable enrich workflow ID 426133266. This avoids depending on run-name. Validation [Run #50 / 45357867951](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45357867951) passed all seven jobs, including every workflow YAML file.

ENRICH_PROGRESS.json was advanced from the verified Run #14 summaries and current Neon cursors. The next bounded enrich run is required to live-test the stable-workflow-ID controller and must not be treated as completion.
## Throughput tuning for next enrichment runs — 2026-11-24

The current in-flight Run #15 still uses the previous 10,000-row probe window. Starting with the next run, `.github/workflows/enrich.yml` uses `--limit 2000` while keeping `--fetch-cap 400`, `--probe-workers 1`, retry cooldowns, and `--sleep 0.7` unchanged. The rationale is that recent worker summaries show essentially no pre-fetch skips and each 10,000-row probe window has about 9,600 fetch candidates; 2,000 rows should still provide well over 400 candidates while cutting unnecessary HEAD probes by 80%. This is a measured tuning hypothesis, not yet accepted. Check the next run's fetched count, cursor delta, 429s, and elapsed time; revert to 10,000 if candidate density falls below the cap or any error pattern appears.
## Full-cycle completion-boundary correction — 2026-11-24

A further audit found 4,974 empty-cosmetics rows with player IDs below the legacy cursor 242336 (1,275 / 1,269 / 1,211 / 1,219 across the four shards). Therefore a worker must **not** be marked complete at its first cursor wrap. `ENRICH_PROGRESS.json` now tracks each worker's `start_cursor=242336` and `wrapped` state; completion is accepted only after the cursor wraps below 242336 and later advances back to or beyond 242336 without an error/429/unexpected abort. The controller was updated accordingly. This prevents missing the low-ID tail.
## Five-worker live Run #15 — 2026-11-24

[Enrich Run #15 / 45358162549](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45358162549) completed successfully across the gate, source preparation, and all five workers. Every worker passed live SP token mint validation and the 64-bucket/four-shard configuration check.

| Worker | fetched | changed | snapshots | gone | errors | pending | cursor |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 400 | 400 | 400 | 0 | 0 | 9,600 | 259095 → 261115 |
| 1 | 400 | 400 | 400 | 4 | 1 | 9,596 | 252396 → 253296 |
| 2 | 400 | 400 | 400 | 2 | 0 | 9,598 | 252392 → 254402 |
| 3 | 400 | 400 | 400 | 0 | 0 | 9,600 | 252368 → 254368 |
| 4 | 400 | 400 | 400 | 2 | 0 | 9,598 | 252369 → 254379 |

Combined: 2,000 fetched, 2,000 changed profiles/snapshots, 8 gone, and one fetch error. Worker 1 hit a Bloxd HTTP 400 throttle during a fetch; its cursor stayed at the first unresolved ID, 253296, so that profile is retried on the next run. The other four workers had zero errors. This is a bounded batch, not full-pass completion.

Four-shard read-only Neon reconciliation after Run #15: 2,925,497 players, 256,149 snapshots, and 0 orphan snapshots. Per-shard player/snapshot totals are 731,408 / 64,009; 731,311 / 64,028; 731,429 / 64,047; and 731,349 / 64,065. The worker cursors are stored in shard-01 meta: 261115 / 253296 / 254402 / 254368 / 254379, with legacy cursor 242336.

### Continuation resilience repair

The first post-run controller delivery was not observed after Run #15, despite the stable workflow ID filter. The controller was hardened in two ways: isolated fetch failures now retry from the unresolved cursor and pause only after the same cursor fails in four consecutive batches; and a five-minute scheduled poll checks for completed, unprocessed enrich runs when GitHub omits a workflow_run delivery. Manual one-off force-ID runs remain excluded from the unattended chain. Public-runner workflow validation passed after the initial controller repair; the follow-up revision is being validated.

## Verified Run #16, source retry fix, and faster probe window — 2026-11-24

[Enrich Run #16 / 45362875074](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45362875074) completed successfully on all five workers using the 2,000-row probe window. The workers reached the unchanged per-worker 400 social-fetch cap in 618–712 seconds; aggregate results were 1,999 updated profiles/snapshots, 7 gone profiles, zero fetch errors, and zero probe HTTP 429s. Worker cursors advanced to 263115 / 256426 / 256407 / 256368 / 256384.

Four-shard read-only reconciliation after Run #16: 2,925,497 players, 258,148 snapshots, and zero orphan snapshots. Per-shard snapshots: 64,508 / 64,525 / 64,550 / 64,565. Per-shard player counts remain 731,408 / 731,311 / 731,429 / 731,349. The full first pass remains in progress: all five cursors are still above the 242336 start boundary and no worker is marked complete.

### Source retry correctness fix

PR [#8](https://github.com/imu31465/bloxd-player-search/pull/8) was independently validated on the public runner and squash-merged to source `runner` at `26bb43760c1344f42cb4238088d3cf0efcfc9108`. A recent per-player `err` journal record previously suppressed the retry for 10 minutes without retaining the player ID in the cursor's unresolved set. The scan could therefore advance past that player before its retry cooldown expired. The merged fix retains recent error IDs as pending until they can be retried. Its focused regression test and all 33 unit tests passed in public-runner validation Run `45364269043`; the merged runner and production validation completed in Run `45364571343`.

### Continuation reliability

The continuation controller now:
- accepts GitHub job-log responses in either ZIP or plain-text form;
- waits/retries when a job log is not immediately available;
- deduplicates workflow-run and scheduled-poll events using the processed run ID;
- handles isolated fetch errors and probe-429 storms with bounded same-cursor retries;
- permits cooldown-deferred rows to remain pending;
- refuses to mark a worker complete until it has wrapped below 242336, returned through the boundary, and has zero errors, probe429s, and pending rows.

Controller implementation at `650c9fb2bd8c34625b510b7c04d4fff08283e597` passed public-runner validation Run `45365950745`. The Run #16 completion was processed by controller job Run `45365691474`, which updated `ENRICH_PROGRESS.json` and dispatched the next run. A five-minute scheduled poll and a push bootstrap are also configured as recovery paths.

### Probe-window optimization

Run #16 confirms that a 2,000-row probe window is substantially larger than the number needed to reach the unchanged 400-fetch cap: each worker left 1,375–1,600 candidates unprobed after hitting the cap. The workflow now reduces the next run's probe window to 1,000 rows, preserving the 400 fetch cap, one probe worker, three 429 cooldown rounds, and 0.7-second inter-fetch delay. This provides a 2.5× candidate buffer at the measured density while halving the HEAD-probe volume compared with 2,000. Run #17 still uses the already-started 2,000-row configuration; verify all five workers on the next run before accepting the 1,000-row setting. Any candidate shortage, probe429, or error pattern requires restoring the previous window or further tuning.

## Verified Run #17 — 2026-11-24

[Enrich Run #17 / 45365831207](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45365831207) completed successfully after source PR #8 merged. The prepare job pinned the merged private source SHA `26bb43760c1344f42cb4238088d3cf0efcfc9108`; gate, prepare, and all five worker jobs succeeded.

| Worker | fetched | changed/snapshots | gone | errors | probe429 | pending | cursor | elapsed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 400 | 400 | 2 | 0 | 0 | 1,598 | 263115 → 265130 | 686s |
| 1 | 400 | 400 | 1 | 0 | 0 | 1,599 | 256426 → 258431 | 704s |
| 2 | 400 | 400 | 4 | 0 | 0 | 1,596 | 256407 → 258427 | 711s |
| 3 | 400 | 400 | 3 | 0 | 0 | 1,597 | 256368 → 258383 | 714s |
| 4 | 400 | 400 | 3 | 0 | 0 | 1,597 | 256384 → 258399 | 698s |

Aggregate: 2,000 updated profiles/snapshots, 13 gone, zero fetch errors, zero probe429. Four-shard reconciliation after the run: 2,925,497 players, 260,148 snapshots, zero orphan snapshots, and 2,671,561 rows whose cosmetics JSON is still empty (an upper bound, not a count of eligible profile fetches). Per-shard player/snapshot/empty-cosmetics counts are 731,408 / 65,007 / 667,953; 731,311 / 65,026 / 667,864; 731,429 / 65,047 / 667,920; and 731,349 / 65,068 / 667,824. Cursors: 265130 / 258431 / 258427 / 258383 / 258399; legacy cursor remains 242336. All worker cycles remain incomplete.

### Probe-window v2

Run #17 confirms the 2,000-row probe setting still fills the per-worker 400-fetch budget, but leaves 1,596–1,599 rows unprobed after the cap. The next bounded run uses `--limit 1000`, leaving a measured 2.5× margin at the current density while halving serial HEAD probes again. The complete public validation run for the 1,000-row workflow revision is `45366651255` (all seven jobs successful). The 1,000-row setting is accepted only after the next live five-worker batch achieves the intended cap without 429/errors or candidate shortage.

### Failed-run recovery path

Controller revision `5f7f28db0085688cd97b9f1f08d7b75cc06ae62b` adds automatic recovery for a completed unsuccessful enrichment workflow: the next scheduled poll records the failed run, re-dispatches a fresh bounded batch, and pauses only after four consecutive failed workflows. The JSON newline serialization correction is `9a5883a562f043a54cb02edb226ef14cf889eb82`. Public workflow validation for the controller revision passed as Run `45367384896`; a live failed-run recovery has not yet been needed to exercise this branch.

## Verified Enrichment Run #37 — 2026-11-24

[Run #37 / 45408097607](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45408097607) completed successfully after all five workers passed live token validation and the four-shard configuration gate. The run still used the pre-optimization runner SHA `26bb43760c1344f42cb4238088d3cf0efcfc9108` and `--limit 1000`.

| Worker | fetched | snapshots | gone | errors | probe429 | pending | cursor | elapsed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 400 | 400 | 4 | 0 | 0 | 596 | 297270 → 299290 | 634s |
| 1 | 400 | 400 | 1 | 0 | 0 | 599 | 290631 → 292636 | 613s |
| 2 | 400 | 400 | 3 | 0 | 0 | 597 | 290552 → 292567 | 582s |
| 3 | 400 | 400 | 0 | 0 | 0 | 600 | 290553 → 292558 | 564s |
| 4 | 400 | 400 | 2 | 0 | 0 | 598 | 290554 → 292564 | 626s |

Aggregate: 2,000 profile updates/snapshots, 10 gone, zero fetch errors and zero probe429. The full-cycle scan remains incomplete; all cursors are still above the 242336 start boundary.

Four-shard read-only reconciliation after Run #37:

| Shard | Players | Snapshots | Empty cosmetics | Orphan snapshots |
|---|---:|---:|---:|---:|
| 01 | 732,280 | 73,609 | 660,256 | 0 |
| 02 | 732,164 | 73,619 | 660,153 | 0 |
| 03 | 732,321 | 73,656 | 660,231 | 0 |
| 04 | 732,273 | 73,675 | 660,167 | 0 |
| **Total** | **2,929,038** | **294,559** | **2,640,807** | **0** |

### Remove redundant probes from the dominant empty-cosmetics path

Source PR [#9](https://github.com/imu31465/bloxd-player-search/pull/9) was squash-merged to `runner` at `02c7174de89055c7363d2a143be009e57ac0ff36`. Empty-cosmetics rows are unconditional social-fetch candidates in the enrichment loop, so their HEAD redirect probes never affected the decision. The runner now bypasses those redundant probes and retains A-gate probing only for profiles whose cosmetics are already populated, where the redirect is needed to detect renames.

The regression suite covers empty and populated cosmetics, and the public-runner validation passed 35 unit tests plus the real four-shard PostgreSQL writer integration test in Run [45410431629](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45410431629). The merged `runner` branch was also checked by the follow-up production validation workflow.

The next batch, [Run #38 / 45410345316](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45410345316), pins the merged runner SHA. The task workflow now uses `--limit 600` rather than 1,000 because empty-cosmetics records no longer consume HEAD probes; the 400 social-fetch cap, one probe worker, and 0.7-second inter-fetch delay remain unchanged. Accept this smaller window only after the live batch proves 400 fetches per worker without errors/429 or candidate shortage.

## Verified Enrichment Run #38 — 2026-11-24

[Run #38 / 45410345316](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45410345316) completed successfully on the merged optimized source runner SHA `02c7174de89055c7363d2a143be009e57ac0ff36`. All five worker jobs fetched/changed 400 profiles each and wrote 400 snapshots each. No worker reported a fetch error or probe HTTP 429.

| Worker | fetched | snapshots | gone | errors | probe429 | pending | cursor | elapsed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 400 | 400 | 0 | 0 | 0 | 600 | 299290 → 301290 | 407s |
| 1 | 400 | 400 | 1 | 0 | 0 | 599 | 292636 → 294646 | 562s |
| 2 | 400 | 400 | 2 | 0 | 0 | 598 | 292567 → 294577 | 544s |
| 3 | 400 | 400 | 0 | 0 | 0 | 600 | 292558 → 294558 | 451s |
| 4 | 400 | 400 | 2 | 0 | 0 | 598 | 292564 → 294579 | 448s |

Aggregate: 2,000 fetched/updated profiles and snapshots, 5 gone, zero errors, zero probe429. Every worker log confirms `probing 0 enriched players (1000 empty-cosmetics rows bypassed)`: all 1,000 rows in each selection window had empty cosmetics and therefore skipped the now-redundant HEAD probes.

**Run #38 still used `--limit 1000`, not 600.** It was dispatched before the `--limit 600` workflow change was pushed. The first live run using 600 is Run #39 / [45412378928](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45412378928). The observed 407–562 second worker durations are already materially lower than the 564–634 seconds in Run #37, before shrinking the window to 600.

Four-shard read-only reconciliation after Run #38:

| Shard | Players | Snapshots | Empty cosmetics | Max player ID | Orphan snapshots |
|---|---:|---:|---:|---:|---:|
| 01 | 732,280 | 74,126 | 659,739 | 3,053,327 | 0 |
| 02 | 732,164 | 74,133 | 659,639 | 3,053,343 | 0 |
| 03 | 732,321 | 74,164 | 659,724 | 3,053,345 | 0 |
| 04 | 732,273 | 74,187 | 659,655 | 3,053,311 | 0 |
| **Total** | **2,929,038** | **296,610** | **2,638,757** | — | **0** |

All five saved cursors remain above the 242336 full-cycle start boundary. The initial full-cursor pass is not complete.

## Verified Enrichment Run #39 — 2026-11-24

[Run #39 / 45412378928](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45412378928) was the first live run using the 600-row selection window. It ran on the optimized source runner SHA `02c7174de89055c7363d2a143be009e57ac0ff36`. All five workers fetched/changed 400 profiles and wrote 400 snapshots each; every worker bypassed all 600 HEAD probes because the selected records had empty cosmetics.

| Worker | fetched | snapshots | gone | errors | probe429 | pending | cursor | elapsed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 400 | 400 | 1 | 0 | 0 | 199 | 301290 → 303295 | 561s |
| 1 | 400 | 400 | 0 | 0 | 0 | 200 | 294646 → 296646 | 542s |
| 2 | 400 | 400 | 4 | 0 | 0 | 196 | 294577 → 296597 | 432s |
| 3 | 400 | 400 | 0 | 0 | 0 | 200 | 294558 → 296563 | 443s |
| 4 | 400 | 400 | 2 | 0 | 0 | 198 | 294579 → 296589 | 481s |

Aggregate: 2,000 fetches/snapshots, 7 gone, zero fetch errors and zero probe429. The five runtimes were 432–561 seconds. This validates the 600-row window at current candidate density; keep the 400-fetch cap and 0.7-second spacing.

Four-shard read-only reconciliation, isolating snapshots written during Run #39:

| Shard | Players | Snapshots written in Run #39 | Empty cosmetics | Max player ID | Orphan snapshots |
|---|---:|---:|---:|---:|---:|
| 01 | 732,280 | 502 | 659,164 | 3,053,327 | 0 |
| 02 | 732,164 | 497 | 659,061 | 3,053,343 | 0 |
| 03 | 732,321 | 498 | 659,144 | 3,053,345 | 0 |
| 04 | 732,273 | 503 | 659,081 | 3,053,311 | 0 |
| **Total** | **2,929,038** | **2,000** | **2,636,450** | — | **0** |

The five saved cursors are 303295 / 296646 / 296597 / 296563 / 296589. They remain above the initial 242336 cycle boundary; full catch-up is still in progress.

### Controller write-race recovery

The controller successfully parsed Run #39 but its first progress push was rejected because another independent validation-workflow commit reached task-repository `main` at the same time. The bounded enrich run itself succeeded. The controller now fetches `origin/main`, rebases its progress-only commit, and retries a non-fast-forward push up to five times. Its push-triggered recovery run succeeded, persisted Run #39, and dispatched Run #40. The shared writer concurrency group remains unchanged.

## Census unresolved-probe retry fix — 2026-11-24

Scheduled census Run #10 / [45385928930](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45385928930) failed closed because two workers ended with 11 and 4 unresolved HEAD probes. The other two shard writers had written receipts, but the finalizer did not run. Crucially, the persisted `census_frontier_cursor` remained at 3,013,345, so the next census plan will retry the same range instead of skipping the incomplete shards.

Source PR [#10](https://github.com/imu31465/bloxd-player-search/pull/10) merged to `runner` at `b6af77e8e91c4cce515eb9ec05bf31df8a094755`. Census runs now make a second pass over all unresolved IDs (including IDs below the moving-horizon tail) while preserving the horizon recheck. The append-only progress journal is summarized by each ID's latest result: a recovered error is accepted, but any ID still ending in `err`, missing coverage, or out-of-range data continues to block shard receipts. Public validation Run [45414008055](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45414008055) passed 39 unit tests, the real four-shard PostgreSQL writer integration test, the merged main/runner checks, Altare integration tests, health/login checks, and workflow YAML validation.

The first enrichment run on the PR #10 runner, [Run #40 / 45414746981](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45414746981), is active. The next scheduled census will be the live test of the retry fix on the retained frontier range.

## Verified Enrichment Run #40 — 2026-11-24

[Run #40 / 45414746981](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45414746981) completed successfully on the exact merged source runner SHA `b6af77e8e91c4cce515eb9ec05bf31df8a094755` (PR #10 census retry fix). All five workers fetched/changed 400 profiles and wrote 400 snapshots each; every worker bypassed all 600 HEAD probes because all selected rows had empty cosmetics.

| Worker | fetched | snapshots | gone | errors | probe429 | pending | cursor | elapsed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 400 | 400 | 2 | 0 | 0 | 198 | 303295 → 305310 | 556s |
| 1 | 400 | 400 | 2 | 0 | 0 | 198 | 296646 → 298656 | 444s |
| 2 | 400 | 400 | 4 | 0 | 0 | 196 | 296597 → 298617 | 510s |
| 3 | 400 | 400 | 1 | 0 | 0 | 199 | 296563 → 298568 | 583s |
| 4 | 400 | 400 | 2 | 0 | 0 | 198 | 296589 → 298599 | 550s |

Aggregate: 2,000 profile updates/snapshots, 11 gone, zero fetch errors, zero probe429, and zero HEAD probes. Worker times were 444–583 seconds. The 600-row window continues to provide more than the 400-profile fetch budget without any redundant probes.

Four-shard read-only reconciliation:

| Shard | Players | New snapshots in Run #40 | Total snapshots | Empty cosmetics | Max player ID | Orphan snapshots |
|---|---:|---:|---:|---:|---:|---:|
| 01 | 732,280 | 502 | 75,087 | 658,783 | 3,053,327 | 0 |
| 02 | 732,164 | 504 | 75,093 | 658,680 | 3,053,343 | 0 |
| 03 | 732,321 | 496 | 75,117 | 658,772 | 3,053,345 | 0 |
| 04 | 732,273 | 498 | 75,137 | 658,707 | 3,053,311 | 0 |
| **Total** | **2,929,038** | **2,000** | **300,434** | **2,634,942** | — | **0** |

Saved cursors: 305310 / 298656 / 298617 / 298568 / 298599. All five still need to pass the current maximum ID, wrap below the initial 242336 cursor, and advance back through that boundary. The full initial pass remains incomplete.

The notify-controller job succeeded and automatically dispatched [Run #41 / 45416901099](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45416901099), which is now active. The controller progress commit uses fetch/rebase/retry to avoid losing progress when another task-repository commit lands concurrently.

## Five-worker live Run #48 — 2026-11-24

[Enrich continuation Run #48 / 45431879918](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45431879918) completed all five worker jobs. Run #48 did **not** complete all 400 fetches on four workers: Bloxd began returning consecutive HTTP 502 responses, followed by a failed periodic session re-mint. Those workers correctly retained the first unresolved profile ID in their cursor.

| Worker | fetched | changed | snapshots | gone | errors | pending | cursor |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 400 | 400 | 400 | 3 | 0 | 197 | 319335 → 321350 |
| 1 | 381 | 381 | 381 | 0 | 8 | 219 | 312726 → 314631 |
| 2 | 377 | 377 | 377 | 1 | 6 | 222 | 310148 → 312042 |
| 3 | 372 | 372 | 372 | 2 | 8 | 226 | 312593 → 314468 |
| 4 | 375 | 375 | 375 | 0 | 7 | 225 | 312654 → 314529 |

Combined: 1,905 successful profile fetches/snapshots, 6 gone, and 29 failed profile requests. The failure logs show sustained Bloxd HTTP 502 responses shortly before the periodic token re-mint was rejected. The cursors remain at each worker's earliest unresolved ID; they must be retried rather than skipped.

Four-shard read-only Neon reconciliation after Run #48: 2,929,038 players, 315,841 snapshots, 0 orphan snapshots, and 2,619,552 empty-cosmetics rows. Per-shard player/snapshot totals are 732,280 / 78,935; 732,164 / 78,947; 732,321 / 78,970; and 732,273 / 78,989. Maximum player IDs remain 3,053,327 / 3,053,343 / 3,053,345 / 3,053,311.

### Recoverable re-mint handling

The previous controller paused on the first "re-mint unavailable after retries" outcome and stopped parsing later worker summaries after the first failed worker. The controller now parses all five jobs, accepts this specific error-plus-retained-cursor case as recoverable, and continues from the earliest unresolved ID. Repeated failure at the same unresolved cursor still pauses after four consecutive batches. Run #49 must validate the new branch. The full-pass cycle boundary remains 242336; no worker has completed its wrap.

## Verified enrichment Run #49 — 2026-11-24

[Run #49 / 45446125712](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45446125712) completed all five workers on source runner SHA `b6af77e8e91c4cce515eb9ec05bf31df8a094755` (PR #10). Each worker selected 600 empty-cosmetics rows, skipped all HEAD probes, and completed 400 profile fetches.

| Worker | fetched | snapshots | gone | errors | probe429 | pending | cursor |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 400 | 400 | 1 | 0 | 0 | 199 | 321350 → 323360 |
| 1 | 400 | 400 | 1 | 0 | 0 | 199 | 314631 → 316636 |
| 2 | 400 | 400 | 0 | 0 | 0 | 200 | 312042 → 314042 |
| 3 | 400 | 400 | 0 | 1 | 0 | 200 | 314468 → 314733 |
| 4 | 400 | 400 | 5 | 0 | 0 | 195 | 314529 → 316554 |

Combined: 2,000 successful fetches/snapshots, 7 gone, one fetch error (HTTP 502). The failed worker3 ID is retained at cursor 314733; controller retry_count is 1. No cursor was moved past the unresolved ID.

Four-shard read-only reconciliation after Run #49:

| Shard | Players | Snapshots | Empty cosmetics | Max player ID | Orphan snapshots |
|---|---:|---:|---:|---:|---:|
| 01 | 732,280 | 79,435 | 654,439 | 3,053,327 | 0 |
| 02 | 732,164 | 79,444 | 654,337 | 3,053,343 | 0 |
| 03 | 732,321 | 79,473 | 654,418 | 3,053,345 | 0 |
| 04 | 732,273 | 79,489 | 654,361 | 3,053,311 | 0 |
| **Total** | **2,929,038** | **317,841** | **2,617,555** | — | **0** |

The persisted worker cursors are 323360 / 316636 / 314042 / 314733 / 316554; the legacy cursor remains 242336. The full five-worker cycle is still in progress; none has wrapped.

## Census replay Run #11 — 2026-11-24

Census Run #10 / 45385928930 failed closed on 11 and 4 unresolved probe IDs in two shards, leaving `census_frontier_cursor=3013345` unchanged. After source PR #10 (merged runner SHA `b6af77e8e91c4cce515eb9ec05bf31df8a094755`) added the unresolved-ID second pass, one targeted manual replay was dispatched as [Run #11 / 45448123052](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45448123052). It processes the same retained frontier range; no manual cursor advance was made. All four scan receipts and the finalizer must pass before the frontier is accepted. Census and enrichment share `player-search-writers`; the enrichment controller waits for census completion.
