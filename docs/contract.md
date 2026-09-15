# Analytics event and reporting contract (DDD-131)

## Ingestion — `POST /v1/events`

- Max body: **4 KiB**
- Reject unknown fields (`extra=forbid`)
- No client project id, no client timestamp (bucket by **server UTC date**)
- No secret in the desktop client

### v1 payload (completed conversions only)

| Field | Type | Allowed |
| --- | --- | --- |
| `schema_version` | int | `1` |
| `event` | string | `conversion_completed` |
| `app_version` | string | short dotted version (`1.2.0`) |
| `rekordbox_version` | string | from XML `PRODUCT@Version` only |
| `surface` | string | `gui` \| `cli` |
| `output_format` | string | `wav` \| `aiff` |
| `bit_depth` | string | `16` \| `24` (selected ceiling) |
| `sample_rate` | string | `44100` \| `48000` |
| `outcomes.converted` | int | 0–10000 |
| `outcomes.copied` | int | 0–10000 |
| `outcomes.skipped` | int | 0–10000 |
| `outcomes.appended` | int | 0–10000 |
| `install_id` | string | optional UUID (`8-4-4-4-12` hex). Omit for legacy clients. Persist one UUID per desktop install. |

### Valid example

```json
{
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
}
```

### Invalid examples

Unknown field / client project id (reject):

```json
{
  "schema_version": 1,
  "event": "conversion_completed",
  "project_id": "rpc",
  "app_version": "1.2.0",
  "rekordbox_version": "7.0.5",
  "surface": "gui",
  "output_format": "wav",
  "bit_depth": "24",
  "sample_rate": "48000",
  "outcomes": {"converted": 1, "copied": 0, "skipped": 0, "appended": 1}
}
```

Unsupported schema version:

```json
{
  "schema_version": 2,
  "event": "conversion_completed",
  "app_version": "1.2.0",
  "rekordbox_version": "7.0.5",
  "surface": "cli",
  "output_format": "aiff",
  "bit_depth": "16",
  "sample_rate": "44100",
  "outcomes": {"converted": 0, "copied": 1, "skipped": 0, "appended": 1}
}
```

### Responses (never echo the payload)

| HTTP | Body |
| --- | --- |
| 202 | `{"status":"accepted"}` |
| 400 | `{"status":"invalid"}` |
| 413 | `{"status":"oversized"}` |
| 422 | `{"status":"unsupported"}` |
| 429 | `{"status":"rate_limited"}` |

## Reporting — `GET /v1/report`

Bearer-authenticated. Includes trusted `project_id` / `project_name` from config.

### Example

```json
{
  "reporting_schema_version": 1,
  "project_id": "rekordbox-playlist-converter",
  "project_name": "Rekordbox Playlist Converter",
  "from": "2026-09-01",
  "to": "2026-09-14",
  "unique_installs": 1,
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

Query params (implemented in DDD-133): `from`, `to`, optional `group_by` and dimension filters.
