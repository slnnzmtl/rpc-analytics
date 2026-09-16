"""SQLite aggregate store — UPSERT only, never raw events."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from rpc_analytics.contract import (
    INPUT_FILE_TYPE_KEYS,
    ConversionCompletedEvent,
    ConversionFailedEvent,
    IngestEvent,
    InstallEvent,
)

INPUT_FILE_TYPE_COLUMNS = tuple(f"input_{key}" for key in INPUT_FILE_TYPE_KEYS)

SCHEMA = """
CREATE TABLE IF NOT EXISTS aggregates (
    day TEXT NOT NULL,
    app_version TEXT NOT NULL,
    rekordbox_version TEXT NOT NULL,
    surface TEXT NOT NULL,
    output_format TEXT NOT NULL,
    bit_depth TEXT NOT NULL,
    sample_rate TEXT NOT NULL,
    converted INTEGER NOT NULL DEFAULT 0,
    copied INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    appended INTEGER NOT NULL DEFAULT 0,
    input_mp3 INTEGER NOT NULL DEFAULT 0,
    input_wav INTEGER NOT NULL DEFAULT 0,
    input_aiff INTEGER NOT NULL DEFAULT 0,
    input_flac INTEGER NOT NULL DEFAULT 0,
    input_m4a INTEGER NOT NULL DEFAULT 0,
    input_alac INTEGER NOT NULL DEFAULT 0,
    input_other INTEGER NOT NULL DEFAULT 0,
    event_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (
        day, app_version, rekordbox_version, surface,
        output_format, bit_depth, sample_rate
    )
);
CREATE TABLE IF NOT EXISTS install_days (
    day TEXT NOT NULL,
    install_hash TEXT NOT NULL,
    PRIMARY KEY (day, install_hash)
);
CREATE TABLE IF NOT EXISTS install_aggregates (
    day TEXT NOT NULL,
    app_version TEXT NOT NULL,
    surface TEXT NOT NULL,
    event_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, app_version, surface)
);
CREATE TABLE IF NOT EXISTS failure_aggregates (
    day TEXT NOT NULL,
    app_version TEXT NOT NULL,
    surface TEXT NOT NULL,
    reason TEXT NOT NULL,
    event_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, app_version, surface, reason)
);
"""

_INPUT_COLS_SQL = ", ".join(INPUT_FILE_TYPE_COLUMNS)
_INPUT_PLACEHOLDERS = ", ".join("?" for _ in INPUT_FILE_TYPE_COLUMNS)
_INPUT_UPSERT_ADD = ",\n    ".join(
    f"{col} = {col} + excluded.{col}" for col in INPUT_FILE_TYPE_COLUMNS
)

UPSERT = f"""
INSERT INTO aggregates (
    day, app_version, rekordbox_version, surface,
    output_format, bit_depth, sample_rate,
    converted, copied, skipped, appended,
    {_INPUT_COLS_SQL},
    event_count
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {_INPUT_PLACEHOLDERS}, 1)
ON CONFLICT(
    day, app_version, rekordbox_version, surface,
    output_format, bit_depth, sample_rate
) DO UPDATE SET
    converted = converted + excluded.converted,
    copied = copied + excluded.copied,
    skipped = skipped + excluded.skipped,
    appended = appended + excluded.appended,
    {_INPUT_UPSERT_ADD},
    event_count = event_count + 1;
"""

INSTALL_DAY_INSERT = """
INSERT OR IGNORE INTO install_days (day, install_hash) VALUES (?, ?);
"""

INSTALL_UPSERT = """
INSERT INTO install_aggregates (day, app_version, surface, event_count)
VALUES (?, ?, ?, 1)
ON CONFLICT(day, app_version, surface) DO UPDATE SET
    event_count = event_count + 1;
"""

FAILURE_UPSERT = """
INSERT INTO failure_aggregates (day, app_version, surface, reason, event_count)
VALUES (?, ?, ?, ?, 1)
ON CONFLICT(day, app_version, surface, reason) DO UPDATE SET
    event_count = event_count + 1;
"""


def _install_hash(install_id: str) -> str:
    return hashlib.sha256(install_id.encode("utf-8")).hexdigest()[:32]


def _input_file_type_counts(event: ConversionCompletedEvent) -> tuple[int, ...]:
    if event.input_file_types is None:
        return tuple(0 for _ in INPUT_FILE_TYPE_KEYS)
    counts = event.input_file_types
    return tuple(getattr(counts, key) for key in INPUT_FILE_TYPE_KEYS)


def _migrate_aggregates(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(aggregates)")}
    for column in INPUT_FILE_TYPE_COLUMNS:
        if column not in existing:
            conn.execute(
                f"ALTER TABLE aggregates ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0"
            )


class AggregateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            _migrate_aggregates(conn)
            conn.commit()

    def check_writable(self) -> bool:
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1 FROM aggregates LIMIT 1;")
                conn.execute("PRAGMA user_version;")
            return True
        except sqlite3.Error:
            return False

    def upsert_event(self, event: IngestEvent, day: date | None = None) -> None:
        bucket = (day or datetime.now(timezone.utc).date()).isoformat()
        with self._connect() as conn:
            if isinstance(event, ConversionCompletedEvent):
                conn.execute(
                    UPSERT,
                    (
                        bucket,
                        event.app_version,
                        event.rekordbox_version,
                        event.surface.value,
                        event.output_format.value,
                        event.bit_depth.value,
                        event.sample_rate.value,
                        event.outcomes.converted,
                        event.outcomes.copied,
                        event.outcomes.skipped,
                        event.outcomes.appended,
                        *_input_file_type_counts(event),
                    ),
                )
            elif isinstance(event, InstallEvent):
                conn.execute(
                    INSTALL_UPSERT,
                    (bucket, event.app_version, event.surface.value),
                )
            elif isinstance(event, ConversionFailedEvent):
                conn.execute(
                    FAILURE_UPSERT,
                    (
                        bucket,
                        event.app_version,
                        event.surface.value,
                        event.reason.value,
                    ),
                )
            if event.install_id:
                conn.execute(
                    INSTALL_DAY_INSERT,
                    (bucket, _install_hash(event.install_id)),
                )
            conn.commit()

    def count_unique_installs(self, from_date: str, to_date: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT install_hash) AS n
                FROM install_days
                WHERE day >= ? AND day <= ?
                """,
                (from_date, to_date),
            ).fetchone()
        return int(row["n"] if row else 0)

    def query_installs(
        self,
        from_date: str,
        to_date: str,
        *,
        filters: dict[str, str] | None = None,
        group_by: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        filters = filters or {}
        allowed_dims = {
            "date": "day",
            "app_version": "app_version",
            "surface": "surface",
        }
        where = ["day >= ?", "day <= ?"]
        params: list[Any] = [from_date, to_date]
        for key, column in allowed_dims.items():
            if key == "date":
                continue
            if key in filters:
                where.append(f"{column} = ?")
                params.append(filters[key])

        if group_by:
            group_cols = []
            for name in group_by:
                if name not in allowed_dims:
                    raise ValueError(f"unsupported install group_by: {name}")
                group_cols.append(allowed_dims[name])
            select_list = []
            for name in ("date", "app_version", "surface"):
                if name in group_by:
                    col = allowed_dims[name]
                    select_list.append(f"{col} AS {name}" if name != "date" else "day AS date")
                else:
                    select_list.append(f"NULL AS {name}" if name != "date" else "MIN(day) AS date")
            sql = f"""
                SELECT {', '.join(select_list)},
                       SUM(event_count) AS event_count
                FROM install_aggregates
                WHERE {' AND '.join(where)}
                GROUP BY {', '.join(group_cols)}
                ORDER BY 1
            """
        else:
            sql = f"""
                SELECT day AS date, app_version, surface, event_count
                FROM install_aggregates
                WHERE {' AND '.join(where)}
                ORDER BY day, app_version, surface
            """

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for key in ("date", "app_version", "surface"):
                if item.get(key) is None:
                    item[key] = ""
            result.append(item)
        return result

    def query_failures(
        self,
        from_date: str,
        to_date: str,
        *,
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        filters = filters or {}
        where = ["day >= ?", "day <= ?"]
        params: list[Any] = [from_date, to_date]
        for key, column in (("app_version", "app_version"), ("surface", "surface")):
            if key in filters:
                where.append(f"{column} = ?")
                params.append(filters[key])

        sql = f"""
            SELECT day AS date, app_version, surface, reason, event_count
            FROM failure_aggregates
            WHERE {' AND '.join(where)}
            ORDER BY day, app_version, surface, reason
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def query(
        self,
        from_date: str,
        to_date: str,
        *,
        filters: dict[str, str] | None = None,
        group_by: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        filters = filters or {}
        allowed_dims = {
            "date": "day",
            "app_version": "app_version",
            "rekordbox_version": "rekordbox_version",
            "surface": "surface",
            "output_format": "output_format",
            "bit_depth": "bit_depth",
            "sample_rate": "sample_rate",
        }
        where = ["day >= ?", "day <= ?"]
        params: list[Any] = [from_date, to_date]
        for key, column in allowed_dims.items():
            if key == "date":
                continue
            if key in filters:
                where.append(f"{column} = ?")
                params.append(filters[key])

        if group_by:
            group_cols = []
            for name in group_by:
                if name not in allowed_dims:
                    raise ValueError(f"unsupported group_by: {name}")
                group_cols.append(allowed_dims[name])
            select_dims = ", ".join(
                f"{col} AS {name}" if name != "date" else "day AS date"
                for name, col in ((n, allowed_dims[n]) for n in group_by)
            )
            # Fill missing dimensions with empty string for AggregateRow compatibility
            all_dim_aliases = []
            for name, col in allowed_dims.items():
                if name in group_by:
                    all_dim_aliases.append(f"{col} AS {name}" if name != "date" else "day AS date")
                else:
                    all_dim_aliases.append(f"'' AS {name}" if name != "date" else "MIN(day) AS date")
            # Simpler: when grouping, return grouped keys + sums; pad other dims
            select_list = []
            for name in (
                "date",
                "app_version",
                "rekordbox_version",
                "surface",
                "output_format",
                "bit_depth",
                "sample_rate",
            ):
                if name in group_by:
                    col = allowed_dims[name]
                    select_list.append(f"{col} AS {name}" if name != "date" else "day AS date")
                else:
                    select_list.append(f"NULL AS {name}" if name != "date" else "MIN(day) AS date")
            input_sums = ", ".join(f"SUM({col}) AS {col}" for col in INPUT_FILE_TYPE_COLUMNS)
            sql = f"""
                SELECT {', '.join(select_list)},
                       SUM(converted) AS converted,
                       SUM(copied) AS copied,
                       SUM(skipped) AS skipped,
                       SUM(appended) AS appended,
                       {input_sums},
                       SUM(event_count) AS event_count
                FROM aggregates
                WHERE {' AND '.join(where)}
                GROUP BY {', '.join(group_cols)}
                ORDER BY 1
            """
        else:
            input_cols = ", ".join(INPUT_FILE_TYPE_COLUMNS)
            sql = f"""
                SELECT day AS date, app_version, rekordbox_version, surface,
                       output_format, bit_depth, sample_rate,
                       converted, copied, skipped, appended,
                       {input_cols},
                       event_count
                FROM aggregates
                WHERE {' AND '.join(where)}
                ORDER BY day, app_version, rekordbox_version, surface,
                         output_format, bit_depth, sample_rate
            """

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for key in (
                "date",
                "app_version",
                "rekordbox_version",
                "surface",
                "output_format",
                "bit_depth",
                "sample_rate",
            ):
                if item.get(key) is None:
                    item[key] = ""
            for col in INPUT_FILE_TYPE_COLUMNS:
                if item.get(col) is None:
                    item[col] = 0
            result.append(item)
        return result
