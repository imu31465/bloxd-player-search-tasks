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
| `census.yml` | Every 30 minutes + manual | Four parallel ID-range workers; shared moving frontier |
| `sweep.yml` | Every 30 minutes + manual | Five concurrent social-profile sweep workers |
| `enrich.yml` | Daily + manual | Profile enrichment drip / selected IDs |
| `name-scan.yml` | Manual | Four-character name availability scan |
| `source-pr-validation.yml` | Manual + workflow-file update | Test merged source `main`/`runner` and merged Altare `main`, run PostgreSQL integration suites on disposable services, verify runner secrets with read-only Neon SELECTs, and lint workflow YAML |
| `production-availability.yml` | Every 15 minutes + manual + monitor-file update | Check the public gateway, all four Neon shards, and the login page; send Discord alert only when a check fails |

Each workflow checks out the private source repository's `runner` branch using
the read-only `DEPLOY_KEY` repository secret.

## Cutover lock

Production writers use the tracked root file `CUTOVER.json` as a fail-closed
switch. Every writer workflow reads it before starting any work:
- `enabled: false` or an invalid/missing file means **no writer jobs run**.
- `enabled: true` allows the scheduled/manual jobs to run.
- A commit changing only `CUTOVER.json` starts one initial census and sweep;
  enrich remains on its daily schedule to avoid an unnecessary extra social-API
  burst at activation.

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
both runs reach their expected completion states, then let the daily enrich
schedule resume. Keep the old single-database schedules disabled; never run old
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
- The tracked `CUTOVER.json` switch remains `enabled: false` until public gateway, authenticated reads, CSV, live token, and four-shard writer checks all pass. Do not start old and new writers concurrently.
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
- `CUTOVER.json` was enabled at commit `8a3597ec179e0e7a80601631907bd10b41e6d004` after the `enabled: false` dry-run workflows both completed successfully with every writer job skipped. Initial census run [#24](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45179485652) completed successfully: all 4 scan partitions finished with zero per-chunk probe errors, found 31,877 records, added 30,000 new players, and protected 1,877 enriched existing rows. Direct read-only checks after finalization show 2,902,783 players and 241,919 snapshots across the four targets, with 0 orphan snapshots; the next frontier cursor is 3,013,345 (2,000-ID overlap). Initial sweep run [#24](https://github.com/imu31465/bloxd-player-search-tasks/actions/runs/45179485667) passed its gate and prepare; all five shard workers have successfully mint-validated the current Bloxd token and are still processing profile refreshes. Enrich resumes on its daily schedule. Keep the original source database intact for rollback.
