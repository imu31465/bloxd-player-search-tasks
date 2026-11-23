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
| `source-pr-validation.yml` | Manual + workflow-file update | Test merged source `main`/`runner` and merged Altare `main`, run PostgreSQL integration suites on disposable services, and verify runner secrets with read-only Neon SELECTs |

Each workflow checks out the private source repository's `runner` branch using
the read-only `DEPLOY_KEY` repository secret.

## Cutover lock

All production jobs require the repository variable
`PLAYER_SEARCH_SHARD_CUTOVER=ready`. If it is missing or has any other value,
jobs are skipped. The validation workflow is independent of this gate. This keeps
production schedules inert while the Neon migration, writer branch, and Altare
reader are being verified.

**Do not set this variable until all of the following are true:**

1. The shard-aware writer changes are merged into the private source
   repository's `runner` branch and its exact-head tests pass.
2. The source-to-shard migration has completed and reported
   `VERIFICATION PASSED`, including all 64 bucket checks and total row counts.
3. The shard-aware Altare reader is deployed and its ID/name/former-name search,
   profiles/history, lists, sorting, pagination, CSV, changes, and health checks
   pass against all four shards.
4. The four repository secrets below are configured with the intended
   four distinct Neon projects. The non-secret project/bucket maps are pinned
   in the workflow files.

The schedules are present but the gate prevents them from running jobs until
the cutover is explicitly enabled.

## Repository variable

Open **Settings → Secrets and variables → Actions → Variables** and add only:

| Name | Value |
|---|---|
| `PLAYER_SEARCH_SHARD_CUTOVER` | Leave unset until every cutover condition above is verified; then set to `ready` |

The non-secret `SHARD_PROJECT_IDS` map is pinned directly in all four workflow
files so this repository does not need a manually configured copy. The map
must be kept in sync with the four project URLs in the secrets and with the
local migration/Altare environment. The application rejects duplicate IDs,
including different branch endpoints that belong to one Neon project.

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

After the checks above pass, set the repository variable
`PLAYER_SEARCH_SHARD_CUTOVER` to `ready`. Then verify one manual run of each
workflow before retiring the corresponding Player Search schedules from
`scheduled-tasks`. Keep the old schedules until the new repository has
successfully run against the migrated data; never run old single-database and
new sharded writers concurrently during the migration/cutover window.

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
- Altare PR #1 was merged to `main` at `caa16600106e3d7a4d851a8219d346eefacd251b` and deployed to Vercel Production. The production `/health` endpoint returned `200` with four healthy shards; `/login` returned `200`.
- Cloudflare Worker `bloxd-player-search-gateway` was updated to forward to `bloxd-player-search-altare.vercel.app`. Cloudflare reports the new version deployed at 100% traffic and the `ORIGIN_SECRET` binding remains present.
- Altare Production now uses `ALTARE=0` and a shared encrypted `ORIGIN_SECRET` with Cloudflare. A fresh Production redeploy is READY; direct requests to the Vercel `/health` and `/login` origins both return `403 Forbidden`. Cloudflare Worker secret version 5 is deployed at 100% traffic. The public Worker HTTP path still needs an external smoke check because the planner runtime cannot reach `workers.dev`.
- The scheduled-runner workflow gate `PLAYER_SEARCH_SHARD_CUTOVER=ready` must remain unset until the public Worker route and authenticated read/write smoke tests have been verified. Do not start old and new writers concurrently.
- The source project `little-dew-38530794` exhausted its November monthly storage allowance. The user approved removing all eight backup/test branches; the cleanup is verified and only the `production` branch remains (`ready`). The historical monthly allowance may remain exhausted until its December 1 reset. The original production branch and source data remain intact.

The validation workflow now checks merged source `main`, source `runner`, and Altare `main`, rather than obsolete topic branches. The workflow-file update was committed as `6577a35f55a62d42aba0f47645cf332dee81a90d` and triggers the public-runner validation workflow. Its post-update run result has not yet been independently retrieved.

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
| Scheduled workflows | New public workflows remain gated; `PLAYER_SEARCH_SHARD_CUTOVER` is still unset |

**Remaining external smoke checks before enabling the schedule gate:** open the public gateway health URL (`https://ltfahel1733.workers.dev/health`) from a normal browser and verify it returns `{"status":"ok","shards":4}`; then sign in through the gateway and verify a real player search and representative read-only pages. The planner runtime cannot itself access `workers.dev` due outbound host restrictions, and the authenticated application password is not available to the planner. Do not send the password in chat.

The source production branch is still retained as a rollback copy. Do not enable the scheduled writer gate or retire the old service until the gateway and authenticated application checks pass.
