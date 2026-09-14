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
- In-memory rate limit keyed by salted IP hash (salt rotates daily).
- No Docker socket mount; `no-new-privileges`; read-only root filesystem.
- Public Caddy allowlists `/v1/events` and `/health` only; filter remote IP and
  forwarded-for from access logs; do not log bodies.
- Reporting bound for localhost access with Bearer token; not on public `:443`.
