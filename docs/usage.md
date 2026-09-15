# Usage guide

How to use the live Rekordbox Playlist Converter analytics service.

Public base URL: `https://analytics.kazansky.dev`  
Legacy public URL: `https://rpc-analytics.slnnzmtl.xyz` (same allowlist)  
App bind (operators only): `127.0.0.1:8091`

Desktop clients **only** call public ingest. They never call `/v1/report` and never
receive `REPORT_TOKEN`.

---

## Health

```bash
curl -sS https://analytics.kazansky.dev/health
# {"status":"ok"}
```

On the VPS:

```bash
curl -sS http://127.0.0.1:8091/health
```

---

## Send an event (public ingest)

`POST /v1/events` — no authentication. Max body **4 KiB**. Unknown fields are rejected.
Only send after a **successful** conversion (not dry-run, preview, cancel, or failure).

### Valid example

```bash
curl -sS -X POST https://analytics.kazansky.dev/v1/events \
  -H 'content-type: application/json' \
  -d '{
    "schema_version": 1,
    "event": "conversion_completed",
    "app_version": "1.2.0",
    "rekordbox_version": "7.0.5",
    "surface": "gui",
    "output_format": "wav",
    "bit_depth": "24",
    "sample_rate": "48000",
    "outcomes": {
      "converted": 12,
      "copied": 3,
      "skipped": 1,
      "appended": 15
    }
  }'
# {"status":"accepted"}   HTTP 202
```

### Field reference

| Field | Values |
| --- | --- |
| `schema_version` | `1` |
| `event` | `conversion_completed` |
| `app_version` | short dotted version (`1.2.0`) |
| `rekordbox_version` | from XML `PRODUCT@Version` only |
| `surface` | `gui` \| `cli` |
| `output_format` | `wav` \| `aiff` |
| `bit_depth` | `16` \| `24` (selected ceiling) |
| `sample_rate` | `44100` \| `48000` |
| `outcomes.*` | integers `0`–`10000` |

Do **not** send `project_id`, client timestamps, track/file paths, or raw XML.

### Response codes

| HTTP | Body | Meaning |
| --- | --- | --- |
| 202 | `{"status":"accepted"}` | Aggregated |
| 400 | `{"status":"invalid"}` | Bad JSON / fields / ranges |
| 413 | `{"status":"oversized"}` | Body over 4 KiB |
| 422 | `{"status":"unsupported"}` | Wrong `schema_version` or `event` |
| 429 | `{"status":"rate_limited"}` | Too many requests from this client |

Failures on the client must be ignored; conversion must continue.

Full contract examples: [contract.md](contract.md).

---

## Read reports (operators)

Reporting and the dashboard are on the public site. `GET /v1/report` requires
`Authorization: Bearer …` with either:

- `REPORT_TOKEN` from `.env` (curl / federation), or
- a Supabase access token for an email in `DASHBOARD_ALLOWED_EMAILS`
  (default `slonanezametil@gmail.com`).

### Dashboard

```bash
open https://analytics.kazansky.dev/dashboard
```

Sign in with the allowlisted Supabase email and password. The page stores the
session in `sessionStorage` for that browser tab and calls `GET /v1/report` with
the access token. Charts cover daily outcomes, surface, format, app /
Rekordbox mix, and ungrouped rows.

Localhost still works (`http://127.0.0.1:8091/dashboard`) if you prefer an SSH tunnel.

### On the VPS (curl)

```bash
cd /root/containers/02-private/analytic-system
export REPORT_TOKEN="$(grep '^REPORT_TOKEN=' .env | cut -d= -f2-)"

curl -sS -H "Authorization: Bearer $REPORT_TOKEN" \
  "http://127.0.0.1:8091/v1/report?from=2026-09-01&to=2026-09-14"
```

### From your laptop (SSH tunnel)

```bash
ssh -L 8091:127.0.0.1:8091 root@91.99.109.18
# then, in another terminal:
curl -sS -H "Authorization: Bearer $REPORT_TOKEN" \
  'http://127.0.0.1:8091/v1/report?from=2026-09-01&to=2026-09-14'
```

### Query parameters

| Param | Required | Notes |
| --- | --- | --- |
| `from` | no | `YYYY-MM-DD` (UTC). Default: today |
| `to` | no | `YYYY-MM-DD` (UTC). Default: today |
| `group_by` | no | Comma list: `date`, `app_version`, `rekordbox_version`, `surface`, `output_format`, `bit_depth`, `sample_rate` |
| `app_version`, `rekordbox_version`, `surface`, `output_format`, `bit_depth`, `sample_rate` | no | Exact-match filters |

Examples:

```bash
# GUI-only rows for one day
curl -sS -H "Authorization: Bearer $REPORT_TOKEN" \
  'http://127.0.0.1:8091/v1/report?from=2026-09-14&to=2026-09-14&surface=gui'

# Totals by app version
curl -sS -H "Authorization: Bearer $REPORT_TOKEN" \
  'http://127.0.0.1:8091/v1/report?from=2026-09-01&to=2026-09-14&group_by=app_version'
```

### Auth failures

| HTTP | Meaning |
| --- | --- |
| 401 | Missing / malformed Bearer, or invalid Supabase JWT |
| 403 | Wrong `REPORT_TOKEN`, or valid JWT whose email is not allowlisted |
| 503 | Neither `REPORT_TOKEN` nor Supabase is configured |

### Example report body

```json
{
  "reporting_schema_version": 1,
  "project_id": "rekordbox-playlist-converter",
  "project_name": "Rekordbox Playlist Converter",
  "from": "2026-09-01",
  "to": "2026-09-14",
  "rows": [
    {
      "date": "2026-09-14",
      "app_version": "1.2.0",
      "rekordbox_version": "7.0.5",
      "surface": "gui",
      "output_format": "wav",
      "bit_depth": "24",
      "sample_rate": "48000",
      "converted": 12,
      "copied": 3,
      "skipped": 1,
      "appended": 15,
      "event_count": 1
    }
  ]
}
```

`project_id` / `project_name` come from server config, not from clients.

---

## Quick smoke checklist

```bash
# Public
curl -sS https://analytics.kazansky.dev/health
curl -sS -o /dev/null -w '%{http_code}\n' https://analytics.kazansky.dev/dashboard   # expect 200
curl -sS -o /dev/null -w '%{http_code}\n' https://analytics.kazansky.dev/v1/report    # expect 401
curl -sS -H "Authorization: Bearer $REPORT_TOKEN" \
  "https://analytics.kazansky.dev/v1/report?from=$(date -u +%F)&to=$(date -u +%F)"

# Private bind still works on the VPS / tunnel
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8091/dashboard          # expect 200
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8091/v1/report               # expect 401
```

---

## Related docs

| Doc | Purpose |
| --- | --- |
| [contract.md](contract.md) | Full ingest/report schemas |
| [deploy.md](deploy.md) | Bring-up and Caddy |
| [operations.md](operations.md) | Backup, restore, upgrade, rollback |
| [architecture.md](architecture.md) | Single-project / frontend-only design |
| [federation.md](federation.md) | Future multi-service dashboard |
| [threat-model.md](threat-model.md) | Why ingest stays on this VPS |
