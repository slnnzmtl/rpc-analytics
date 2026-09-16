#!/usr/bin/env python3
"""Seed synthetic conversion events with install_id for local / demo dashboards.

Usage (inside the container or against SQLITE_PATH):

  python scripts/seed_synthetic.py
  python scripts/seed_synthetic.py --reset

Posts are written through AggregateStore (same path as ingest), so past UTC days
can be filled. Safe for demo volumes only — --reset wipes aggregates + install_days.
"""

from __future__ import annotations

import argparse
import os
import random
import uuid
from datetime import date, timedelta

from rpc_analytics.contract import ConversionCompletedEvent
from rpc_analytics.store import AggregateStore

APP_VERSIONS = ("1.1.0", "1.2.0")
RB_VERSIONS = ("6.8.5", "7.0.5", "7.1.0")
SURFACES = ("gui", "cli")
FORMATS = ("wav", "aiff")
DEPTHS = ("16", "24")
RATES = ("44100", "48000")


def _event(install_id: str, rng: random.Random) -> ConversionCompletedEvent:
    converted = rng.randint(1, 80)
    copied = rng.randint(0, max(1, converted // 8))
    skipped = rng.randint(0, max(1, converted // 12))
    return ConversionCompletedEvent.model_validate(
        {
            "schema_version": 1,
            "event": "conversion_completed",
            "app_version": rng.choice(APP_VERSIONS),
            "rekordbox_version": rng.choice(RB_VERSIONS),
            "surface": rng.choices(SURFACES, weights=(4, 1), k=1)[0],
            "output_format": rng.choices(FORMATS, weights=(5, 1), k=1)[0],
            "bit_depth": rng.choices(DEPTHS, weights=(1, 4), k=1)[0],
            "sample_rate": rng.choice(RATES),
            "outcomes": {
                "converted": converted,
                "copied": copied,
                "skipped": skipped,
                "appended": converted + copied,
            },
            "input_file_types": {
                "mp3": rng.randint(0, converted),
                "wav": rng.randint(0, max(1, converted // 4)),
                "aiff": rng.randint(0, max(1, converted // 6)),
                "flac": rng.randint(0, max(1, converted // 5)),
                "m4a": rng.randint(0, max(1, converted // 8)),
                "alac": rng.randint(0, max(1, converted // 10)),
                "other": rng.randint(0, 2),
            },
            "install_id": install_id,
        }
    )


def seed(*, reset: bool, days: int, users: int, seed: int) -> None:
    path = os.environ.get("SQLITE_PATH", "/data/analytics.db")
    store = AggregateStore(path)
    rng = random.Random(seed)
    installs = [str(uuid.UUID(int=rng.getrandbits(128))) for _ in range(users)]

    if reset:
        with store._connect() as conn:
            conn.execute("DELETE FROM aggregates;")
            conn.execute("DELETE FROM install_days;")
            conn.commit()

    today = date.today()  # container clock is UTC in this deploy
    end = today
    start = end - timedelta(days=days - 1)

    events = 0
    day = start
    while day <= end:
        # More activity mid-range; each day picks a subset of installs.
        active = rng.sample(installs, k=rng.randint(max(3, users // 5), min(users, users // 2 + 3)))
        for install_id in active:
            for _ in range(rng.randint(1, 3)):
                store.upsert_event(_event(install_id, rng), day=day)
                events += 1
        day += timedelta(days=1)

    unique = store.count_unique_installs(start.isoformat(), end.isoformat())
    print(
        f"seeded events={events} unique_installs={unique} "
        f"range={start.isoformat()}..{end.isoformat()} db={path}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="Wipe aggregates and install_days first")
    parser.add_argument("--days", type=int, default=14, help="UTC days to fill ending today")
    parser.add_argument("--users", type=int, default=36, help="Synthetic distinct install_ids")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility")
    args = parser.parse_args()
    seed(reset=args.reset, days=args.days, users=args.users, seed=args.seed)


if __name__ == "__main__":
    main()
