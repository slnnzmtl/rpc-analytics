# Analytics event and reporting contract (DDD-131)

## Ingestion — `POST /v1/events`

- Max body: **4 KiB**
- Reject unknown fields (`extra=forbid`)
- No client project id, no client timestamp (bucket by **server UTC date**)
- No secret in the desktop client
- `event` is `install` (one-shot on first opt-in), `conversion_completed`, or `conversion_failed`

### v1 payload — `install`

Slim body. Do **not** send conversion fields (`rekordbox_version`, `output_format`, `bit_depth`, `sample_rate`, `outcomes`). Counts toward `unique_installs` only; does not increment conversion aggregates.

| Field | Type | Allowed |
| --- | --- | --- |
| `schema_version` | int | `1` |
| `event` | string | `install` |
| `app_version` | string | short dotted version (`1.2.0`) |
| `surface` | string | `gui` \| `cli` |
| `install_id` | string | required UUID (`8-4-4-4-12` hex). Persist one UUID per desktop install. |

### Valid `install` example

```json
{
  "schema_version": 1,
  "event": "install",
  "app_version": "1.2.0",
  "surface": "gui",
  "install_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
}
```

### v1 payload — `conversion_failed`

Slim body like `install`, plus a closed failure `reason`. Do **not** send conversion
fields (`rekordbox_version`, `output_format`, `bit_depth`, `sample_rate`, `outcomes`,
`input_file_types`) or free-text messages / paths. Counts toward `unique_installs`;
does not increment conversion aggregates. Send only after a **failed conversion job**
(not dry-run, preview, or cancel).

| Field | Type | Allowed |
| --- | --- | --- |
| `schema_version` | int | `1` |
| `event` | string | `conversion_failed` |
| `app_version` | string | short dotted version (`1.2.0`) |
| `surface` | string | `gui` \| `cli` |
| `install_id` | string | required UUID (`8-4-4-4-12` hex). Persist one UUID per desktop install. |
| `reason` | string | `xml_parse` \| `encode` \| `config` \| `unknown` |

### Valid `conversion_failed` example

```json
{
  "schema_version": 1,
  "event": "conversion_failed",
  "app_version": "1.2.0",
  "surface": "gui",
  "install_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  "reason": "xml_parse"
}
```

### v1 payload — `conversion_completed`

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
| `input_file_types` | object | optional; per-batch counts of **source** files by extension bucket |
| `input_file_types.mp3` | int | 0–10000 |
| `input_file_types.wav` | int | 0–10000 |
| `input_file_types.aiff` | int | 0–10000 |
| `input_file_types.flac` | int | 0–10000 |
| `input_file_types.m4a` | int | 0–10000 |
| `input_file_types.alac` | int | 0–10000 |
| `input_file_types.other` | int | 0–10000; AAC/unknown extensions not listed above |
| `install_id` | string | optional UUID (`8-4-4-4-12` hex). Omit for legacy clients. Persist one UUID per desktop install. |

### Valid `conversion_completed` example

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
}
```

### Invalid examples

`install` with conversion fields (reject):

```json
{
  "schema_version": 1,
  "event": "install",
  "app_version": "1.2.0",
  "surface": "gui",
  "install_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  "outcomes": {"converted": 1, "copied": 0, "skipped": 0, "appended": 1}
}
```

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
      "input_mp3": 4,
      "input_wav": 2,
      "input_aiff": 1,
      "input_flac": 3,
      "input_m4a": 1,
      "input_alac": 0,
      "input_other": 1,
      "event_count": 1
    }
  ],
  "install_rows": [
    {
      "date": "2026-09-14",
      "app_version": "1.2.0",
      "surface": "gui",
      "event_count": 1
    }
  ],
  "failure_rows": [
    {
      "date": "2026-09-14",
      "app_version": "1.2.0",
      "surface": "gui",
      "reason": "xml_parse",
      "event_count": 1
    }
  ]
}
```

`rows` are `conversion_completed` aggregates. `install_rows` are `event=install`
aggregates (by UTC day, app version, and surface). `failure_rows` are
`event=conversion_failed` aggregates (by UTC day, app version, surface, and
reason). `unique_installs` is distinct hashed `install_id` values from all event
types in range.

Query params (implemented in DDD-133): `from`, `to`, optional `group_by` and dimension filters.
