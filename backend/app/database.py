import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIRECTORY / ".env")

DEFAULT_DATABASE_NAME = "securevoice"
MONGODB_SERVER_SELECTION_TIMEOUT_MS = 5000
MONGODB_CONNECT_TIMEOUT_MS = 5000
MONGODB_SOCKET_TIMEOUT_MS = 10000
logger = logging.getLogger(__name__)
_client_lock = threading.Lock()
_client: MongoClient | None = None
_client_key: tuple[str, str] | None = None


class AlertStoreError(Exception):
    """A safe, user-facing alert persistence failure."""


def mongodb_is_configured() -> bool:
    return bool(os.environ.get("MONGODB_URI", "").strip())


def _get_alerts_collection() -> Collection:
    global _client, _client_key

    uri = os.environ.get("MONGODB_URI", "").strip()
    if not uri:
        raise AlertStoreError(
            "MongoDB is not configured. Set MONGODB_URI in the backend environment."
        )
    database_name = (
        os.environ.get("MONGODB_DATABASE", DEFAULT_DATABASE_NAME).strip()
        or DEFAULT_DATABASE_NAME
    )
    key = (uri, database_name)

    with _client_lock:
        if _client is None or _client_key != key:
            if _client is not None:
                _client.close()
            try:
                _client = MongoClient(
                    uri,
                    serverSelectionTimeoutMS=MONGODB_SERVER_SELECTION_TIMEOUT_MS,
                    connectTimeoutMS=MONGODB_CONNECT_TIMEOUT_MS,
                    socketTimeoutMS=MONGODB_SOCKET_TIMEOUT_MS,
                    appname="SecureVoiceAI",
                )
                _client.admin.command("ping")
                _client_key = key
            except PyMongoError as error:
                logger.error("MongoDB client configuration failed: %s", type(error).__name__)
                if _client is not None:
                    _client.close()
                _client = None
                _client_key = None
                raise AlertStoreError(
                    "MongoDB could not be configured. Check the backend database settings."
                ) from error

        client = _client
        return client[database_name]["alerts"]


def _utc_timestamp(timestamp: str | datetime) -> datetime:
    if isinstance(timestamp, str):
        try:
            value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Alert timestamp must be a valid ISO-8601 timestamp.") from error
    else:
        value = timestamp
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _serialize(document: dict[str, Any]) -> dict[str, Any]:
    result = dict(document)
    result.pop("_id", None)
    timestamp = result.get("timestamp")
    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        result["timestamp"] = timestamp.astimezone(timezone.utc).isoformat()
    elif timestamp is not None:
        result["timestamp"] = str(timestamp)
    if "event_id" not in result:
        result["event_id"] = str(document.get("_id", ""))
    return result


def initialize_database() -> None:
    collection = _get_alerts_collection()
    try:
        collection.create_index(
            [("timestamp", DESCENDING), ("event_id", DESCENDING)],
            name="recent_alerts",
        )
        collection.create_index(
            [("source", ASCENDING), ("timestamp", DESCENDING)],
            name="alerts_by_source",
        )
        collection.create_index(
            [("event_type", ASCENDING), ("timestamp", DESCENDING)],
            name="alerts_by_type",
        )
    except PyMongoError as error:
        logger.error("MongoDB index initialization failed: %s", type(error).__name__)
        raise AlertStoreError(
            "The alert database could not be initialized."
        ) from error


def check_connection() -> None:
    collection = _get_alerts_collection()
    try:
        collection.database.command("ping")
    except PyMongoError as error:
        logger.error("MongoDB health check failed: %s", type(error).__name__)
        raise AlertStoreError(
            "The alert database is temporarily unavailable."
        ) from error


def close_client() -> None:
    global _client, _client_key
    with _client_lock:
        if _client is not None:
            _client.close()
        _client = None
        _client_key = None


def create_alert(
    timestamp: str,
    event_type: str,
    confidence: float | None,
    alert_message: str,
    *,
    detection_status: str = "recorded",
    source: str = "api",
) -> dict[str, Any]:
    if detection_status not in {"detected", "recorded", "legacy"}:
        raise ValueError("Unsupported alert detection status.")
    if source not in {"uploaded_video", "api", "unknown"}:
        raise ValueError("Unsupported alert source.")

    event_id = uuid4().hex
    alert = {
        "event_id": event_id,
        "timestamp": _utc_timestamp(timestamp),
        "event_type": event_type,
        "confidence": confidence,
        "alert_message": alert_message,
        "detection_status": detection_status,
        "source": source,
        "voice_generation_status": "not_requested",
        "playback_status": "not_played",
    }
    try:
        _get_alerts_collection().insert_one({"_id": event_id, **alert})
    except PyMongoError as error:
        logger.error("MongoDB alert insert failed: %s", type(error).__name__)
        raise AlertStoreError(
            "The alert could not be saved to the database."
        ) from error
    return _serialize(alert)


def _event_id_filter(event_id: int | str) -> dict[str, Any]:
    if isinstance(event_id, str) and event_id.isdecimal():
        return {"event_id": {"$in": [event_id, int(event_id)]}}
    return {"event_id": event_id}


def update_voice_generation(event_id: int | str, status: str) -> bool:
    if status not in {"not_requested", "pending", "generated", "failed"}:
        raise ValueError("Unsupported voice-generation status.")
    try:
        result = _get_alerts_collection().update_one(
            _event_id_filter(event_id),
            {"$set": {"voice_generation_status": status}},
        )
    except PyMongoError as error:
        logger.error("MongoDB voice-status update failed: %s", type(error).__name__)
        raise AlertStoreError(
            "Alert voice status could not be updated."
        ) from error
    return result.matched_count == 1


def update_playback_status(event_id: int | str, status: str) -> bool:
    if status not in {"not_played", "played", "failed"}:
        raise ValueError("Unsupported playback status.")
    try:
        result = _get_alerts_collection().update_one(
            _event_id_filter(event_id),
            {"$set": {"playback_status": status}},
        )
    except PyMongoError as error:
        logger.error("MongoDB playback update failed: %s", type(error).__name__)
        raise AlertStoreError(
            "Alert playback status could not be updated."
        ) from error
    return result.matched_count == 1


def list_alerts(limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    try:
        collection = _get_alerts_collection()
        cursor = (
            collection.find({}, {"_id": 0})
            .sort([("timestamp", DESCENDING), ("event_id", DESCENDING)])
            .skip(offset)
            .limit(limit)
        )
        items = [_serialize(document) for document in cursor]
        total = collection.count_documents({})
    except PyMongoError as error:
        logger.error("MongoDB alert-history read failed: %s", type(error).__name__)
        raise AlertStoreError(
            "The alert database is temporarily unavailable."
        ) from error
    return items, total


def clear_alerts() -> int:
    try:
        result = _get_alerts_collection().delete_many({})
    except PyMongoError as error:
        logger.error("MongoDB alert-history clear failed: %s", type(error).__name__)
        raise AlertStoreError(
            "Alert history could not be cleared."
        ) from error
    return result.deleted_count


def upsert_migrated_alert(alert: dict[str, Any]) -> bool:
    """Insert one legacy alert only when its deterministic migration ID is absent."""
    event_id = alert["event_id"]
    document = {
        **alert,
        "_id": f"sqlite-alert-{event_id}",
        "event_id": event_id,
        "timestamp": _utc_timestamp(alert["timestamp"]),
        "detection_status": alert.get("detection_status") or "legacy",
        "source": alert.get("source") or "unknown",
    }
    try:
        result = _get_alerts_collection().update_one(
            {"_id": document["_id"]},
            {"$setOnInsert": document},
            upsert=True,
        )
    except PyMongoError as error:
        logger.error("MongoDB legacy-alert migration failed: %s", type(error).__name__)
        raise AlertStoreError(
            "A legacy alert could not be copied to the database."
        ) from error
    return result.upserted_id is not None
