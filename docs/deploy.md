# Deploy (frontend VPS)

## Prerequisites

- DNS A record: `rpc-analytics.slnnzmtl.xyz` → frontend public IP (`91.99.109.18`)
- Docker + Compose
- Caddy reverse proxy project at `/root/containers/01-reverse-proxy`

## Configure

```bash
cd /root/containers/02-private/analytic-system
cp .env.example .env
# Set REPORT_TOKEN and RATE_LIMIT_SALT_SEED to long random values
# Do not commit .env
```

## Start

```bash
docker compose up -d --build
curl -sS http://127.0.0.1:8091/health
```

## Caddy

Public site allowlists `/v1/events` and `/health` only. Reporting stays on
`127.0.0.1:8091` and is reached via SSH local-forward:

```bash
ssh -L 8091:127.0.0.1:8091 user@frontend-vps
curl -sS -H "Authorization: Bearer $REPORT_TOKEN" \
  'http://127.0.0.1:8091/v1/report?from=2026-09-01&to=2026-09-14'
```

Optional later: Tailscale Serve for `/v1/report` (not installed on this host today).

## Smoke checklist

1. `GET /health` → 200
2. Invalid ingest → 400
3. Valid ingest → 202
4. Public `https://rpc-analytics.slnnzmtl.xyz/v1/report` → 404 (Caddy allowlist)
5. Authorized report on localhost → 200 with project metadata
6. Unauthorized report → 401/403

## Isolation

The CRM/agents backend VPS must have no analytics route, tunnel, volume, or
forwarding credential for this service.
