"""SQLite aggregate store — UPSERT only, never raw events."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from rpc_analytics.contract import ConversionCompletedEvent

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
    event_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (
        day, app_version, rekordbox_version, surface,
        output_format, bit_depth, sample_rate
    )
);
"""

UPSERT = """
INSERT INTO aggregates (
    day, app_version, rekordbox_version, surface,
    output_format, bit_depth, sample_rate,
    converted, copied, skipped, appended, event_count
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
ON CONFLICT(
    day, app_version, rekordbox_version, surface,
    output_format, bit_depth, sample_rate
) DO UPDATE SET
    converted = converted + excluded.converted,
    copied = copied + excluded.copied,
    skipped = skipped + excluded.skipped,
    appended = appended + excluded.appended,
    event_count = event_count + 1;
"""


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

    def check_writable(self) -> bool:
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1 FROM aggregates LIMIT 1;")
                conn.execute("PRAGMA user_version;")
            return True
        except sqlite3.Error:
            return False

    def upsert_event(self, event: ConversionCompletedEvent, day: date | None = None) -> None:
        from datetime import datetime, timezone

        bucket = (day or datetime.now(timezone.utc).date()).isoformat()
        with self._connect() as conn:
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
                ),
            )
            conn.commit()

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
            sql = f"""
                SELECT {', '.join(select_list)},
                       SUM(converted) AS converted,
                       SUM(copied) AS copied,
                       SUM(skipped) AS skipped,
                       SUM(appended) AS appended,
                       SUM(event_count) AS event_count
                FROM aggregates
                WHERE {' AND '.join(where)}
                GROUP BY {', '.join(group_cols)}
                ORDER BY 1
            """
        else:
            sql = f"""
                SELECT day AS date, app_version, rekordbox_version, surface,
                       output_format, bit_depth, sample_rate,
                       converted, copied, skipped, appended, event_count
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
            result.append(item)
        return result
