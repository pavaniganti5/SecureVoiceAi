import os
import logging
import tempfile
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, AsyncGenerator
from uuid import UUID

from fastapi import (
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import database
from app import murf_service
from app.database import AlertStoreError
from app.detection import (
    ModelUnavailableError,
    VideoProcessingCancelled,
    VideoProcessingError,
    analyze_video,
)
from app.schemas import (
    AlertClearResponse,
    AlertCreate,
    AlertListResponse,
    AlertResponse,
    DetectionConfig,
    PersonEntryEvent,
    PlaybackStatusResponse,
    PlaybackStatusUpdate,
    VideoDetectionResponse,
    VoiceServiceStatus,
)

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
ALLOWED_VIDEO_CONTENT_TYPES = {
    "application/octet-stream",
    "video/mp4",
    "video/quicktime",
    "video/avi",
    "video/msvideo",
    "video/vnd.avi",
    "video/x-msvideo",
    "application/x-troff-msvideo",
    "video/x-matroska",
    "video/webm",
}
_analysis_cancel_events: dict[UUID, threading.Event] = {}
_analysis_cancel_lock = threading.Lock()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    if database.mongodb_is_configured():
        database.initialize_database()
    else:
        logger.warning(
            "MongoDB is not configured; alert persistence and API health checks will be unavailable"
        )
    try:
        yield
    finally:
        database.close_client()


app = FastAPI(
    title="SecureVoice AI API",
    description=(
        "Local video person-detection and alert-history API with Murf AI text-to-speech. "
        "Live webcam monitoring is not connected."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(AlertStoreError)
async def handle_database_error(_: object, error: AlertStoreError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(error)},
    )


configured_frontend_origins = [
    origin.strip()
    for origin in os.environ.get("FRONTEND_ORIGIN", "").split(",")
    if origin.strip()
]
allowed_origins = configured_frontend_origins or [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-Analysis-ID"],
)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    database.check_connection()
    return {"status": "ok", "database": "connected"}


@app.post(
    "/api/alerts",
    response_model=AlertResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_alert(alert: AlertCreate) -> dict:
    timestamp = datetime.now(timezone.utc).isoformat()
    return database.create_alert(
        timestamp=timestamp,
        event_type=alert.event_type,
        confidence=alert.confidence,
        alert_message=alert.alert_message,
        detection_status="recorded",
        source="api",
    )


@app.get("/api/alerts", response_model=AlertListResponse)
def get_alerts(
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AlertListResponse:
    items, total = database.list_alerts(limit, offset)
    response.headers["Cache-Control"] = "no-store"
    return AlertListResponse(items=items, total=total)


@app.delete("/api/alerts", response_model=AlertClearResponse)
def delete_alerts() -> AlertClearResponse:
    return AlertClearResponse(deleted_count=database.clear_alerts())


@app.get("/api/voice/status", response_model=VoiceServiceStatus)
def voice_service_status(response: Response) -> VoiceServiceStatus:
    response.headers["Cache-Control"] = "no-store"
    return VoiceServiceStatus(
        configured=murf_service.murf_is_configured(),
        voice_id=murf_service.murf_voice_id(),
        model="GEN2",
    )


@app.post(
    "/api/alerts/{event_id}/playback",
    response_model=PlaybackStatusResponse,
)
def update_alert_playback(
    event_id: str,
    update: PlaybackStatusUpdate,
) -> PlaybackStatusResponse:
    if not database.update_playback_status(event_id, update.status):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert history entry was not found.",
        )
    return PlaybackStatusResponse(event_id=event_id, playback_status=update.status)


@app.post(
    "/api/detection/video",
    response_model=VideoDetectionResponse,
    status_code=status.HTTP_200_OK,
)
def detect_people_in_video(
    video: Annotated[UploadFile, File(description="A local video clip to analyze")],
    analysis_id: Annotated[UUID, Header(alias="X-Analysis-ID")],
    confidence: Annotated[float, Form(ge=0.1, le=1)] = 0.35,
    roi_x: Annotated[float, Form(ge=0, le=1)] = 0,
    roi_y: Annotated[float, Form(ge=0, le=1)] = 0,
    roi_width: Annotated[float, Form(gt=0, le=1)] = 1,
    roi_height: Annotated[float, Form(gt=0, le=1)] = 1,
    cooldown_seconds: Annotated[int, Form(ge=0, le=3600)] = 10,
) -> VideoDetectionResponse:
    original_name = video.filename or "uploaded-video"
    suffix = Path(original_name.replace("\\", "/")).suffix.lower()
    content_type = (video.content_type or "application/octet-stream").lower()
    if suffix not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Supported video extensions are MP4, MOV, AVI, MKV, and WebM.",
        )
    if content_type not in ALLOWED_VIDEO_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The uploaded content type is not a supported video format.",
        )
    if roi_x + roi_width > 1 or roi_y + roi_height > 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The normalized monitored region must fit within the video frame.",
        )
    config = DetectionConfig(
        confidence=confidence,
        roi_x=roi_x,
        roi_y=roi_y,
        roi_width=roi_width,
        roi_height=roi_height,
        cooldown_seconds=cooldown_seconds,
    )

    temporary_path: Path | None = None
    cancel_event = threading.Event()
    with _analysis_cancel_lock:
        if analysis_id in _analysis_cancel_events:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An analysis with this ID is already running.",
            )
        _analysis_cancel_events[analysis_id] = cancel_event
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=suffix, prefix="securevoice-", delete=False
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            total_bytes = 0
            while chunk := video.file.read(UPLOAD_CHUNK_BYTES):
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Video upload exceeds the 100 MB limit.",
                    )
                temporary_file.write(chunk)

        try:
            analysis = analyze_video(temporary_path, config, cancel_event)
        except VideoProcessingCancelled as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Video analysis was stopped.",
            ) from error
        except ModelUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error
        except VideoProcessingError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error

        persisted_events: list[PersonEntryEvent] = []
        for event in analysis["region_entry_events"]:
            stored = database.create_alert(
                timestamp=datetime.now(timezone.utc).isoformat(),
                event_type="person_entered_roi",
                confidence=event["confidence"],
                alert_message=event["alert_message"],
                detection_status="detected",
                source="uploaded_video",
            )

            database.update_voice_generation(stored["event_id"], "pending")
            try:
                generated_speech = murf_service.generate_speech(event["alert_message"])
            except murf_service.MurfServiceError as error:
                database.update_voice_generation(stored["event_id"], "failed")
                persisted_events.append(
                    PersonEntryEvent(
                        event_id=stored["event_id"],
                        media_time_seconds=event["media_time_seconds"],
                        confidence=event["confidence"],
                        alert_message=event["alert_message"],
                        voice_generation_status="failed",
                        voice_error=str(error),
                    )
                )
                continue

            database.update_voice_generation(stored["event_id"], "generated")
            persisted_events.append(
                PersonEntryEvent(
                    event_id=stored["event_id"],
                    media_time_seconds=event["media_time_seconds"],
                    confidence=event["confidence"],
                    alert_message=event["alert_message"],
                    voice_generation_status="generated",
                    audio_base64=generated_speech.audio_base64,
                    audio_content_type=generated_speech.audio_content_type,
                )
            )

        safe_filename = os.path.basename(original_name.replace("\\", "/"))
        analysis["region_entry_events"] = persisted_events
        return VideoDetectionResponse(
            filename=safe_filename,
            **analysis,
        )
    finally:
        with _analysis_cancel_lock:
            _analysis_cancel_events.pop(analysis_id, None)
        video.file.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


@app.post("/api/detection/cancel/{analysis_id}")
def cancel_video_analysis(analysis_id: UUID) -> dict[str, bool]:
    with _analysis_cancel_lock:
        cancel_event = _analysis_cancel_events.get(analysis_id)
        if cancel_event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active analysis was found for this ID.",
            )
        cancel_event.set()
    return {"cancel_requested": True}
