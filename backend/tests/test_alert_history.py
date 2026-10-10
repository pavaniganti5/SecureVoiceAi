import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import database, main
from scripts.migrate_sqlite_to_mongodb import migrate


class FakeUpdateResult:
    def __init__(self, matched_count=0, upserted_id=None):
        self.matched_count = matched_count
        self.upserted_id = upserted_id


class FakeDeleteResult:
    def __init__(self, deleted_count):
        self.deleted_count = deleted_count


class FakeCursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, fields):
        for field, direction in reversed(fields):
            self.documents.sort(
                key=lambda document: document.get(field),
                reverse=direction < 0,
            )
        return self

    def skip(self, count):
        self.documents = self.documents[count:]
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(self.documents)


class FakeCollection:
    def __init__(self):
        self.documents = {}
        self.indexes = []
        self.database = self

    def command(self, command):
        if command != "ping":
            raise AssertionError(f"Unexpected mock database command: {command}")
        return {"ok": 1}

    def create_index(self, keys, **_kwargs):
        self.indexes.append(keys)
        return "mock-index"

    def insert_one(self, document):
        self.documents[document["_id"]] = dict(document)

    def find(self, _query, _projection):
        return FakeCursor([dict(document) for document in self.documents.values()])

    def count_documents(self, _query):
        return len(self.documents)

    def update_one(self, query, update, upsert=False):
        key = query.get("_id")
        document = self.documents.get(key)
        if document is None and upsert:
            self.documents[key] = dict(update["$setOnInsert"])
            return FakeUpdateResult(upserted_id=key)
        if document is None:
            event_filter = query.get("event_id")
            event_ids = (
                event_filter.get("$in", [])
                if isinstance(event_filter, dict)
                else [event_filter]
            )
            matches = [
                item
                for item in self.documents.values()
                if item.get("event_id") in event_ids
            ]
            if not matches:
                return FakeUpdateResult()
            document = matches[0]
        document.update(update.get("$set", {}))
        return FakeUpdateResult(matched_count=1)

    def delete_many(self, _query):
        count = len(self.documents)
        self.documents.clear()
        return FakeDeleteResult(count)


class AlertHistoryDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.collection = FakeCollection()
        self.collection_patch = patch.object(
            database, "_get_alerts_collection", return_value=self.collection
        )
        self.collection_patch.start()

    def tearDown(self):
        self.collection_patch.stop()

    def _create(self, timestamp, message):
        return database.create_alert(
            timestamp,
            "person_entered_roi",
            0.9,
            message,
            detection_status="detected",
            source="uploaded_video",
        )

    def test_creation_persists_expected_fields_and_status_defaults(self):
        alert = self._create("2026-01-01T12:00:00+00:00", "Person entered.")
        self.assertTrue(alert["event_id"])
        self.assertEqual(alert["source"], "uploaded_video")
        self.assertEqual(alert["detection_status"], "detected")
        self.assertEqual(alert["voice_generation_status"], "not_requested")
        self.assertIsInstance(alert["timestamp"], str)

    def test_retrieval_is_newest_first_and_supports_pagination(self):
        older = self._create("2026-01-01T12:00:00+00:00", "Older")
        newer = self._create("2026-01-02T12:00:00+00:00", "Newer")
        items, total = database.list_alerts(1, 0)
        next_items, _ = database.list_alerts(1, 1)

        self.assertEqual(total, 2)
        self.assertEqual(items[0]["event_id"], newer["event_id"])
        self.assertEqual(next_items[0]["event_id"], older["event_id"])

    def test_empty_history_returns_zero(self):
        self.assertEqual(database.list_alerts(20, 0), ([], 0))

    def test_missing_mongodb_uri_fails_explicitly_without_sqlite_fallback(self):
        self.collection_patch.stop()
        with patch.dict(os.environ, {"MONGODB_URI": ""}):
            with self.assertRaisesRegex(database.AlertStoreError, "MONGODB_URI"):
                database.list_alerts(10, 0)
        self.collection_patch.start()

    def test_migration_upsert_is_idempotent_and_preserves_legacy_id(self):
        record = {
            "event_id": 42,
            "timestamp": "2025-02-01T00:00:00+00:00",
            "event_type": "person_entered_roi",
            "confidence": 0.7,
            "alert_message": "Legacy event",
            "voice_generation_status": "failed",
            "playback_status": "not_played",
            "detection_status": "legacy",
            "source": "unknown",
        }

        self.assertTrue(database.upsert_migrated_alert(record))
        self.assertFalse(database.upsert_migrated_alert(record))
        items, total = database.list_alerts(10, 0)
        self.assertEqual(total, 1)
        self.assertEqual(items[0]["event_id"], 42)
        self.assertEqual(items[0]["source"], "unknown")

    def test_connection_errors_are_sanitized(self):
        with patch.object(
            database,
            "_get_alerts_collection",
            side_effect=database.AlertStoreError(
                "The alert database is temporarily unavailable."
            ),
        ):
            with self.assertRaisesRegex(database.AlertStoreError, "temporarily unavailable"):
                database.list_alerts(10, 0)

    def test_database_initialization_adds_query_indexes(self):
        database.initialize_database()
        self.assertEqual(len(self.collection.indexes), 3)


class SqliteMigrationTests(unittest.TestCase):
    def test_migration_is_read_only_and_skips_previously_migrated_rows(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "alerts.db"
            with closing(sqlite3.connect(source_path)) as connection:
                with connection:
                    connection.execute(
                        """
                        CREATE TABLE alerts (
                            event_id INTEGER PRIMARY KEY,
                            timestamp TEXT NOT NULL,
                            event_type TEXT NOT NULL,
                            confidence REAL,
                            alert_message TEXT NOT NULL,
                            voice_generation_status TEXT,
                            playback_status TEXT,
                            detection_status TEXT,
                            source TEXT
                        )
                        """
                    )
                    connection.execute(
                        """
                        INSERT INTO alerts VALUES (
                            12, '2026-01-01T00:00:00+00:00', 'person_entered_roi',
                            0.82, 'Migrated event', 'generated', 'played',
                            'detected', 'uploaded_video'
                        )
                        """
                    )

            collection = FakeCollection()
            with patch.object(
                database, "_get_alerts_collection", return_value=collection
            ):
                self.assertEqual(migrate(source_path, dry_run=True), (0, 1))
                self.assertEqual(collection.documents, {})
                self.assertEqual(migrate(source_path), (1, 0))
                self.assertEqual(migrate(source_path), (0, 1))

            with closing(sqlite3.connect(source_path)) as connection:
                source_count = connection.execute(
                    "SELECT COUNT(*) FROM alerts"
                ).fetchone()[0]
            self.assertEqual(source_count, 1)
            migrated = collection.documents["sqlite-alert-12"]
            self.assertEqual(migrated["event_id"], 12)
            self.assertEqual(migrated["source"], "uploaded_video")


class AlertHistoryRouteTests(unittest.TestCase):
    def setUp(self):
        self.collection = FakeCollection()
        self.environment = patch.dict(os.environ, {"MONGODB_URI": ""})
        self.environment.start()
        self.collection_patch = patch.object(
            database, "_get_alerts_collection", return_value=self.collection
        )
        self.collection_patch.start()
        self.client = TestClient(main.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.collection_patch.stop()
        self.environment.stop()

    def test_api_lists_newest_real_alert(self):
        database.create_alert(
            "2026-01-01T12:00:00+00:00",
            "person_entered_roi",
            0.85,
            "An actual event",
            detection_status="detected",
            source="uploaded_video",
        )
        response = self.client.get("/api/alerts")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["items"][0]["alert_message"], "An actual event")

    def test_health_endpoint_checks_database_connectivity(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "database": "connected"},
        )

    def test_api_rejects_invalid_alert_fields(self):
        response = self.client.post(
            "/api/alerts",
            json={
                "event_type": "Person!",
                "confidence": 1.4,
                "alert_message": " ",
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_api_database_failure_returns_safe_service_error(self):
        self.collection_patch.stop()
        with patch.object(
            database,
            "_get_alerts_collection",
            side_effect=database.AlertStoreError(
                "The alert database is temporarily unavailable."
            ),
        ):
            response = self.client.get("/api/alerts")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "The alert database is temporarily unavailable."},
        )
        self.collection_patch.start()


if __name__ == "__main__":
    unittest.main()
