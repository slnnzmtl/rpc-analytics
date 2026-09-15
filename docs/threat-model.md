# Threat notes (frontend-only)

## Chosen model

Public unauthenticated ingest is attacker-controlled JSON by design. Blast radius
is contained by keeping ingest and SQLite on the frontend VPS and keeping the
CRM/agents host off the path entirely.

## Rejected alternatives

- **Ingest on the CRM/agents VPS:** shared kernel/Docker/Caddy with client data;
  unauthenticated POST as neighbor to EspoCRM and agents.
- **Frontend ingest forwarding to backend over Tailscale/mTLS:** authenticates the
  peer, not the payload; gives the public box a write credential into the
  sensitive network.

## Mitigations on this host

- Reject unknown ingestion fields; 4 KiB body limit.
- Aggregate UPSERT only; no raw events, bodies, or IP retention on disk.
  Optional `install_id` is stored only as a truncated SHA-256 hash per UTC day
  (`install_days`); the raw UUID is never written or logged.
- In-memory rate limit keyed by salted IP hash (salt rotates daily).
- No Docker socket mount; `no-new-privileges`; read-only root filesystem.
- Public Caddy allowlists `/v1/events`, `/health`, `/dashboard`, and `/v1/report`;
  report responses require Bearer `REPORT_TOKEN` or a Supabase access token for an
  email in `DASHBOARD_ALLOWED_EMAILS` (verified via Supabase Auth `/user`, not
  `user_metadata`). Only the anon/publishable key is used; never `service_role`.
  Filter remote IP and forwarded-for from access logs; do not log bodies or tokens.
