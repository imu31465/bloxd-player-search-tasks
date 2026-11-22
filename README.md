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

Each workflow checks out the private source repository's `runner` branch using
the read-only `DEPLOY_KEY` repository secret.

## Cutover lock

All production jobs require the repository variable
`PLAYER_SEARCH_SHARD_CUTOVER=ready`. If it is missing or has any other value,
jobs are skipped. This keeps the new workflows inert while the Neon migration,
writer branch, and Altare reader are being verified.

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
