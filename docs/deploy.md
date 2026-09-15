# Deploy (frontend VPS)

## Prerequisites

- DNS A record: `analytics.kazansky.dev` → frontend public IP (`91.99.109.18`)
- Optional legacy: `rpc-analytics.slnnzmtl.xyz` → same IP (still allowlisted in Caddy)
- Docker + Compose
- Caddy reverse proxy project at `/root/containers/01-reverse-proxy`
- Existing Supabase project with user `slonanezametil@gmail.com` (email/password)

## Configure

```bash
cd /root/containers/02-private/analytic-system
cp .env.example .env
# Set REPORT_TOKEN and RATE_LIMIT_SALT_SEED to long random values
# Set SUPABASE_URL and SUPABASE_ANON_KEY from the existing Supabase project
# Confirm DASHBOARD_ALLOWED_EMAILS includes slonanezametil@gmail.com
# Do not commit .env
```

In the Supabase dashboard for that project:

1. Disable public signups if they are still enabled.
2. Auth → URL configuration: add `https://analytics.kazansky.dev` and
   `https://analytics.kazansky.dev/dashboard` (plus `http://127.0.0.1:8091` for
   tunnel use if needed).

## Start

```bash
docker compose up -d --build
curl -sS http://127.0.0.1:8091/health
```

## Caddy

Public site allowlists `/v1/events`, `/health`, `/dashboard`, and `/v1/report`.
Report data requires Bearer `REPORT_TOKEN` or an allowlisted Supabase JWT.
Dashboard UI (Supabase email/password login):

```bash
open https://analytics.kazansky.dev/dashboard
```

Optional SSH local-forward for localhost-only access:

```bash
ssh -L 8091:127.0.0.1:8091 user@frontend-vps
curl -sS -H "Authorization: Bearer $REPORT_TOKEN" \
  'http://127.0.0.1:8091/v1/report?from=2026-09-01&to=2026-09-14'
```

## Smoke checklist

1. `GET /health` → 200
2. Invalid ingest → 400
3. Valid ingest → 202
4. Public `https://analytics.kazansky.dev/v1/report` without Bearer → 401
5. Authorized report (Bearer `REPORT_TOKEN`) → 200 with project metadata
6. Wrong token → 403
7. Public `https://analytics.kazansky.dev/dashboard` → 200 HTML with login form
8. Sign in as allowlisted user → Load reports succeeds

## Isolation

The CRM/agents backend VPS must have no analytics route, tunnel, volume, or
forwarding credential for this service. Do not put `service_role` on this host.
