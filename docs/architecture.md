# Single-project analytics architecture (DDD-130)

## Decision

One analytics service deployment serves **one** configured project. The initial
deployment is Rekordbox Playlist Converter. The same container image can be
reused later as a second Compose project with a different hostname, volume,
`PROJECT_ID` / `PROJECT_NAME`, and `REPORT_TOKEN`.

## Boundaries

| Concern | Rule |
| --- | --- |
| Project identity | Fixed by server env (`PROJECT_ID`, `PROJECT_NAME`). Never accepted from ingestion payloads. |
| Data store | One isolated SQLite volume per Compose project. |
| Ingestion | Public `POST /v1/events` with no client secret. |
| Reporting | `GET /v1/report` accepts Bearer `REPORT_TOKEN` or an allowlisted Supabase user JWT; public via Caddy. Dashboard at `/dashboard` uses Supabase email/password. |
| Multi-tenant | Out of scope. No shared DB, no project registry, no client-supplied project id. |

## Frontend-only runtime

Untrusted public ingest and SQLite live on the **frontend VPS** already meant to
be public. The CRM/agents backend VPS must not receive analytics traffic, store
aggregates, hold a forwarding credential, or proxy reports.

```text
Converter clients  --POST /v1/events-->  Caddy (public TLS)
                                              |
                                              v
                                         rpc-analytics (127.0.0.1)
                                              |
                                              v
                                         SQLite aggregates

Operator  --HTTPS /dashboard (Supabase login)-->  same process
Operator  --Bearer REPORT_TOKEN or JWT /v1/report-->  same process
```

## Reuse for another project

1. Clone this Compose project (new directory / Compose project name).
2. New volume, new `.env` (`PROJECT_ID`, `PROJECT_NAME`, `REPORT_TOKEN`, Supabase settings, salts).
3. New public hostname + Caddy site (ingest, health, dashboard, report).
4. Same image; no shared storage with other deployments.

## Future dashboard federation

A future dashboard registers each service URL and its own token, then fetches
`/v1/report`. It must not merge databases or ingestion, and must never proxy
reports through the CRM/agents backend VPS. See `docs/federation.md` (DDD-133).
