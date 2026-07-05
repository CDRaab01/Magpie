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

## What's deferred to Phase 8

Remote auto-redeploy (a dedicated `magpie` self-hosted runner, `vars.MAGPIE_DIR`, a no-tunnel
`redeploy.ps1`, and the post-deploy synthetic smoke) lands with suite membership in Phase 8, same
shape as the sibling apps minus the tunnel step. Until then, deploys here are a manual
`git pull && docker compose up -d --build` on this host.

## Verify a deploy

`curl http://127.0.0.1:8005/version` locally, or the tailnet HTTPS URL from another
tailnet-joined device. `docs_enabled=false` and the suite's `HSTS_ENABLED`/`TRUST_PROXY` flags
exist for parity but have no proxy shape to turn on for here yet — see `CLAUDE.md` §2.
