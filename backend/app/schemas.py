from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AlertCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event_type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    confidence: float | None = Field(default=None, ge=0, le=1)
    alert_message: str = Field(min_length=1, max_length=500)

    @field_validator("alert_message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Alert message must contain non-whitespace characters")
        return value


class AlertResponse(BaseModel):
    event_id: int | str
    timestamp: str
    event_type: str
    confidence: float | None
    alert_message: str
    detection_status: Literal["detected", "recorded", "legacy"]
    source: Literal["uploaded_video", "api", "unknown"]
    voice_generation_status: Literal["not_requested", "pending", "generated", "failed"]
    playback_status: Literal["not_played", "played", "failed"]


class AlertListResponse(BaseModel):
    items: list[AlertResponse]
    total: int


class AlertClearResponse(BaseModel):
    deleted_count: int


class PlaybackStatusUpdate(BaseModel):
    status: Literal["played", "failed"]


class PlaybackStatusResponse(BaseModel):
    event_id: int | str
    playback_status: Literal["not_played", "played", "failed"]


class VoiceServiceStatus(BaseModel):
    configured: bool
    voice_id: str
    model: str


class DetectionConfig(BaseModel):
    confidence: float = Field(default=0.35, ge=0.1, le=1)
    roi_x: float = Field(default=0, ge=0, le=1)
    roi_y: float = Field(default=0, ge=0, le=1)
    roi_width: float = Field(default=1, gt=0, le=1)
    roi_height: float = Field(default=1, gt=0, le=1)
    cooldown_seconds: int = Field(default=10, ge=0, le=3600)
    inference_fps: int = Field(default=2, ge=1, le=10)

    @model_validator(mode="after")
    def region_must_fit_frame(self) -> "DetectionConfig":
        if self.roi_x + self.roi_width > 1 or self.roi_y + self.roi_height > 1:
            raise ValueError("ROI must fit within the normalized video frame")
        return self


class DetectionBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float


class DetectionRegion(BaseModel):
    x: float
    y: float
    width: float
    height: float


class PersonEntryEvent(BaseModel):
    event_id: int | str
    media_time_seconds: float
    confidence: float
    alert_message: str
    voice_generation_status: Literal["generated", "failed"]
    voice_error: str | None = None
    playback_status: Literal["not_played"] = "not_played"
    audio_base64: str | None = None
    audio_content_type: str | None = None


class VideoDetectionResponse(BaseModel):
    filename: str
    duration_seconds: float
    sampled_frames: int
    person_detections: int
    region_entry_events: list[PersonEntryEvent]
    roi: DetectionRegion
    annotated_frame_jpeg: str | None
    saved_video: bool = False
    processing_time_seconds: float | None = None
