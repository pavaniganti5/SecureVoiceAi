import argparse
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from app import database

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_PATH = BACKEND_DIRECTORY / "data" / "alerts.db"
ALERT_COLUMNS = (
    "event_id",
    "timestamp",
    "event_type",
    "confidence",
    "alert_message",
    "voice_generation_status",
    "playback_status",
)


def read_legacy_alerts(sqlite_path: Path) -> list[dict[str, Any]]:
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"SQLite alert database was not found: {sqlite_path}")

    with closing(
        sqlite3.connect(sqlite_path.as_uri() + "?mode=ro", uri=True)
    ) as connection:
        connection.row_factory = sqlite3.Row
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'alerts'"
        ).fetchone()
        if table is None:
            raise ValueError("SQLite database does not contain an alerts table.")

        available_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(alerts)")
        }
        selected_columns = [
            column for column in ALERT_COLUMNS if column in available_columns
        ]
        optional_columns = [
            column
            for column in ("detection_status", "source")
            if column in available_columns
        ]
        rows = connection.execute(
            f"SELECT {', '.join(selected_columns + optional_columns)} "
            "FROM alerts ORDER BY event_id ASC"
        ).fetchall()

    records = []
    for row in rows:
        record = dict(row)
        record.setdefault("confidence", None)
        record.setdefault("voice_generation_status", "not_requested")
        record.setdefault("playback_status", "not_played")
        record.setdefault("detection_status", "legacy")
        record.setdefault("source", "unknown")
        records.append(record)
    return records


def migrate(sqlite_path: Path, *, dry_run: bool = False) -> tuple[int, int]:
    records = read_legacy_alerts(sqlite_path)
    if dry_run:
        return 0, len(records)

    database.initialize_database()
    inserted = 0
    for record in records:
        if database.upsert_migrated_alert(record):
            inserted += 1
    return inserted, len(records) - inserted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy SQLite alert history into MongoDB without duplicating migrated IDs."
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=DEFAULT_SQLITE_PATH,
        help="Existing SQLite database file (read-only); defaults to backend/data/alerts.db.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count source records without connecting to MongoDB or writing any data.",
    )
    arguments = parser.parse_args()
    inserted, skipped = migrate(arguments.sqlite_path, dry_run=arguments.dry_run)
    if arguments.dry_run:
        print(f"Dry run: {skipped} SQLite alert(s) are available to migrate.")
    else:
        print(f"Migration complete: {inserted} inserted, {skipped} already present.")


if __name__ == "__main__":
    main()
