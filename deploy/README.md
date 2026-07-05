# Magpie — deployment

Self-hosted via Docker Compose, same operational model as the sibling apps — **with one
deliberate difference: no Cloudflare Tunnel, no public hostname.** Magpie is tailnet-only by
design (`CLAUDE.md` §2, §8) because it holds financial data; reachability off this host is via
Tailscale Serve, not a tunnel.

## Ports on this host

| App        | API (localhost)    | Postgres (localhost) |
|------------|---------------------|------------------------|
| Spotter    | 127.0.0.1:8000      | 127.0.0.1:5432         |
| Plate      | 127.0.0.1:8001      | 127.0.0.1:5433         |
| Cookbook   | 127.0.0.1:8003      | 127.0.0.1:5434         |
| Dragonfly  | 127.0.0.1:8004      | 127.0.0.1:5435         |
| **Magpie** | **127.0.0.1:8005**  | **127.0.0.1:5436**     |

## First-time setup

1. `cp server/.env.example server/.env` (Phase 0 needs nothing beyond `DATABASE_URL`, which
   already matches the compose defaults — Phase 1 adds `SECRET_KEY` and the suite SSO vars).
2. `docker compose up -d --build` — migrations run on container boot (a no-op until Phase 1
   adds the first revision).
3. Verify locally: `curl http://127.0.0.1:8005/health` → `{"status":"ok"}`.

## Reachability: Tailscale Serve, not a tunnel

There is no `cloudflared` service in `docker-compose.yml` — that's not an oversight, it's the
security posture (`CLAUDE.md` §8: nothing about Magpie should be reachable from the public
internet). Instead, front the loopback-only server with HTTPS at this host's Tailscale MagicDNS
name:

```powershell
tailscale serve --bg --https=443 http://127.0.0.1:8005
```

Verify the mapping actually took (Tailscale CLI syntax has changed across versions — don't
trust the command above blindly, confirm it):

```powershell
tailscale serve status
```

The Android client then points at `https://<this-host>.<tailnet>.ts.net/` — reachable only to
devices joined to the tailnet (the phone already is, for the ntfy alerts channel). This is also
why the manifest carries no cleartext-traffic exception: Serve terminates real HTTPS, so there's
no bare-IP problem to work around the way Hawksnest has.

## Remote auto-redeploy (Phase 8, as built)

`.github/workflows/deploy.yml` fires on `workflow_run` after CI goes green on `main` (or manual
`workflow_dispatch`, which doubles as a rollback lever — pass a prior SHA). It runs on a
self-hosted runner labeled `magpie` and calls `deploy/redeploy.ps1`, same shape as the sibling
apps' deploy workflows minus the tunnel step.

**One-time host setup** (mirrors the sibling apps' runner setup, e.g. Cookbook's
`C:\actions-runner-cookbook`):
1. Register a new self-hosted runner (GitHub repo → Settings → Actions → Runners → New
   self-hosted runner) at `C:\actions-runner-magpie`, label it `magpie`, install as a Windows
   service (`.\svc.cmd install` / `start`) so it survives reboots.
2. Set the `MAGPIE_DIR` repository Actions **variable** to this canonical clone's path
   (`C:\Code\Magpie`) — the workflow deploys that clone (which owns `server/.env` and the
   `pgdata` volume), never the runner's ephemeral checkout.
3. Reuse the suite's `KEYSTORE_BASE64`/`KEYSTORE_PASSWORD`/`KEY_ALIAS`/`KEY_PASSWORD` secrets
   (same signing key as every sibling app) for `release.yml`.
4. Set `MAGPIE_SMOKE_CLIENT_ID`/`MAGPIE_SMOKE_CLIENT_SECRET` repository **secrets** — a
   dedicated confidential client registered on dragonfly-id's `SMOKE_CLIENTS` (separate from
   the real `magpie` OAuth client; see CLAUDE.md §9 and dragonfly-id's `app/routers/smoke.py`).
   If unset, the post-deploy smoke step logs a warning and skips (the health gate above it
   still runs and still fails the deploy on its own).

**`redeploy.ps1`'s one deliberate addition over the sibling scripts**: a `pg_dump` snapshot
*before* `docker compose up -d --build` (kept in a sibling `magpie-db-backups/` directory,
last 5 retained) — migrations run on container boot against real financial history, so a bad
migration must be a restore, never a loss (CLAUDE.md §9).

**Post-deploy synthetic smoke** (`scripts/synthetic_smoke.py`, run inside the server container):
Magpie is SSO-only, so unlike the sibling apps' smokes there is no `/auth/register` to script.
Instead it mints a suite-audience token from dragonfly-id's dedicated `POST /smoke/token`
(enabled by `SMOKE_CLIENTS` — a small, separately-revocable credential, never the real OAuth
client), trades it for a Magpie session via `POST /auth/suite` exactly like a real sign-in,
then creates → reads → deletes a manual cash transaction.

## Verify a deploy

`curl http://127.0.0.1:8005/version` locally, or the tailnet HTTPS URL from another
tailnet-joined device. `docs_enabled=false` and the suite's `HSTS_ENABLED`/`TRUST_PROXY` flags
exist for parity but have no proxy shape to turn on for here yet — see `CLAUDE.md` §2.
