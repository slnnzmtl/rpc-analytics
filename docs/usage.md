# Usage guide

How to use the live Rekordbox Playlist Converter analytics service.

Public base URL: `https://analytics.slnnzmtl.xyz`  
Legacy public URLs: `https://analytics.kazansky.dev`, `https://rpc-analytics.slnnzmtl.xyz` (same allowlist)  
App bind (operators only): `127.0.0.1:8091`

Desktop clients **only** call public ingest. They never call `/v1/report` and never
receive `REPORT_TOKEN`.

---

## Health

```bash
curl -sS https://analytics.slnnzmtl.xyz/health
# {"status":"ok"}
```

On the VPS:

```bash
curl -sS http://127.0.0.1:8091/health
```

---

## Send an event (public ingest)

`POST /v1/events` — no authentication. Max body **4 KiB**. Unknown fields are rejected.
Do **not** send `project_id`, client timestamps, track/file paths, or raw XML.

`event` is one of:

- `install` — one-shot on first analytics opt-in (required `install_id`; no conversion fields)
- `conversion_completed` — only after a **successful** conversion (not dry-run, preview, or cancel)
- `conversion_failed` — only after a **failed conversion job** (not dry-run, preview, or cancel); required `install_id` and closed `reason`

### Valid `install` example

```bash
curl -sS -X POST https://analytics.slnnzmtl.xyz/v1/events \
  -H 'content-type: application/json' \
  -d '{
    "schema_version": 1,
    "event": "install",
    "app_version": "1.2.0",
    "surface": "gui",
    "install_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
  }'
# {"status":"accepted"}   HTTP 202
```

### Valid `conversion_failed` example

```bash
curl -sS -X POST https://analytics.slnnzmtl.xyz/v1/events \
  -H 'content-type: application/json' \
  -d '{
    "schema_version": 1,
    "event": "conversion_failed",
    "app_version": "1.2.0",
    "surface": "gui",
    "install_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "reason": "xml_parse"
  }'
# {"status":"accepted"}   HTTP 202
```

### Valid `conversion_completed` example

```bash
curl -sS -X POST https://analytics.slnnzmtl.xyz/v1/events \
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
    },
    "input_file_types": {
      "mp3": 4,
      "wav": 2,
      "aiff": 1,
      "flac": 3,
      "m4a": 1,
      "alac": 0,
      "other": 1
    }
  }'
# {"status":"accepted"}   HTTP 202
```

### Field reference

| Field | Values |
| --- | --- |
| `schema_version` | `1` |
| `event` | `install` \| `conversion_completed` \| `conversion_failed` |
| `app_version` | short dotted version (`1.2.0`) |
| `surface` | `gui` \| `cli` |
| `install_id` | UUID (`8-4-4-4-12` hex); required on `install` and `conversion_failed`, optional on `conversion_completed` |
| `reason` | `conversion_failed` only; `xml_parse` \| `encode` \| `config` \| `unknown` |
| `rekordbox_version` | `conversion_completed` only; from XML `PRODUCT@Version` |
| `output_format` | `conversion_completed` only; `wav` \| `aiff` |
| `bit_depth` | `conversion_completed` only; `16` \| `24` (selected ceiling) |
| `sample_rate` | `conversion_completed` only; `44100` \| `48000` |
| `outcomes.*` | `conversion_completed` only; integers `0`–`10000` |
| `input_file_types.*` | `conversion_completed` only; optional object; counts per source extension bucket (`mp3`, `wav`, `aiff`, `flac`, `m4a`, `alac`, `other`), each `0`–`10000` |

### Response codes

| HTTP | Body | Meaning |
| --- | --- | --- |
| 202 | `{"status":"accepted"}` | Aggregated |
| 400 | `{"status":"invalid"}` | Bad JSON / fields / ranges |
| 413 | `{"status":"oversized"}` | Body over 4 KiB |
| 422 | `{"status":"unsupported"}` | Wrong `schema_version` or `event` |
| 429 | `{"status":"rate_limited"}` | Too many requests from this client |

Ingest HTTP failures on the client must be ignored; conversion must continue.

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
open https://analytics.slnnzmtl.xyz/dashboard
```

Sign in with the allowlisted Supabase email and password. The page stores the
session in `sessionStorage` for that browser tab and calls `GET /v1/report` with
the access token. After sign-in (or session restore), the default last-14-UTC-day
range loads automatically and refreshes every minute. Charts cover daily
outcomes, install events (by surface), failed conversions (by reason), surface,
format, source input file types (range totals and per UTC day), app / Rekordbox
mix, and ungrouped rows (including `input_*` columns). The Users stat is
`unique_installs` (distinct hashed `install_id` values from `install`,
`conversion_completed`, and `conversion_failed` events in range). Install events
are also shown as a dedicated daily chart from `install_rows`. Failed conversions
use `failure_rows`.

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
      "input_mp3": 4,
      "input_wav": 2,
      "input_aiff": 1,
      "input_flac": 3,
      "input_m4a": 1,
      "input_alac": 0,
      "input_other": 1,
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
curl -sS https://analytics.slnnzmtl.xyz/health
curl -sS -o /dev/null -w '%{http_code}\n' https://analytics.slnnzmtl.xyz/dashboard   # expect 200
curl -sS -o /dev/null -w '%{http_code}\n' https://analytics.slnnzmtl.xyz/v1/report    # expect 401
curl -sS -H "Authorization: Bearer $REPORT_TOKEN" \
  "https://analytics.slnnzmtl.xyz/v1/report?from=$(date -u +%F)&to=$(date -u +%F)"

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
