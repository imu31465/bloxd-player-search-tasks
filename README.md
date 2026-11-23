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
- **Security blocker:** Altare Production currently has `ALTARE=1`; `app.py` uses that flag to bypass `OriginSecretMiddleware`, so the Vercel origin is not restricted to requests carrying the Cloudflare secret. The Worker sends `X-Origin-Verify`, but Altare does not currently enforce it. Do not treat the gateway cutover as fully secured until a shared `ORIGIN_SECRET` is installed on both sides and a fresh Production deployment proves direct-origin requests return 403 while Worker requests succeed.
- The scheduled-runner workflow gate `PLAYER_SEARCH_SHARD_CUTOVER=ready` must remain unset until the public Worker route and authenticated read/write smoke tests have been verified. Do not start old and new writers concurrently.
- The source project `little-dew-38530794` has exhausted its November monthly storage allowance. Its production branch is retained as a rollback source; redundant backup branches must not be deleted without an explicit retention decision.

The validation workflow now checks the merged Altare `main` branch rather than the obsolete topic branch. Updating this workflow triggers a fresh validation run against current source `main`, source `runner`, Altare `main`, disposable PostgreSQL migration tests, and the four target Neon connection/grant checks.
