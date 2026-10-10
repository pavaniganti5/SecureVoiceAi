import base64
import math
import os
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2
from ultralytics import YOLO

from app.schemas import DetectionConfig

DEFAULT_MODEL = "yolo11n.pt"
INFERENCE_FPS = 5
MAX_VIDEO_SECONDS = 120
MAX_FRAME_PIXELS = 16_000_000
MAX_PREVIEW_WIDTH = 960

_model_lock = threading.Lock()


class VideoProcessingError(Exception):
    """A video could not be opened, decoded, or analyzed."""


class ModelUnavailableError(Exception):
    """The configured YOLO model could not be loaded."""


class VideoProcessingCancelled(Exception):
    """Video analysis was stopped by the user."""


class RegionEntryCooldown:
    def __init__(self, cooldown_seconds: int) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.previous_roi_occupied = False
        self.last_event_media_time = float("-inf")

    def observe(
        self,
        occupied: bool,
        confidence: float | None,
        media_time: float,
    ) -> float | None:
        is_entry = occupied and not self.previous_roi_occupied
        cooldown_complete = (
            media_time - self.last_event_media_time >= self.cooldown_seconds
        )
        self.previous_roi_occupied = occupied
        if not is_entry or not cooldown_complete or confidence is None:
            return None

        self.last_event_media_time = media_time
        return confidence


@lru_cache(maxsize=1)
def get_model() -> YOLO:
    model_path = os.environ.get("SECUREVOICE_YOLO_MODEL", DEFAULT_MODEL)
    with _model_lock:
        try:
            return YOLO(model_path)
        except Exception as error:
            raise ModelUnavailableError(
                "The YOLO model could not be loaded. Check the model name, installation, "
                "and internet access for the first-time model download."
            ) from error


def _annotate(
    frame: Any,
    detections: list[dict[str, float | int]],
    roi: DetectionConfig,
) -> Any:
    height, width = frame.shape[:2]
    roi_start = (round(roi.roi_x * width), round(roi.roi_y * height))
    roi_end = (
        round((roi.roi_x + roi.roi_width) * width),
        round((roi.roi_y + roi.roi_height) * height),
    )
    cv2.rectangle(frame, roi_start, roi_end, (170, 145, 245), 2)
    cv2.putText(
        frame,
        "MONITORED REGION",
        (roi_start[0] + 5, max(20, roi_start[1] - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (190, 170, 255),
        2,
        cv2.LINE_AA,
    )
    for detection in detections:
        start = (int(detection["x1"]), int(detection["y1"]))
        end = (int(detection["x2"]), int(detection["y2"]))
        cv2.rectangle(frame, start, end, (80, 215, 160), 2)
        cv2.putText(
            frame,
            f"Person {float(detection['confidence']):.2f}",
            (start[0], max(20, start[1] - 7)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (80, 215, 160),
            2,
            cv2.LINE_AA,
        )
    return frame


def _encode_preview(frame: Any) -> str:
    height, width = frame.shape[:2]
    if width > MAX_PREVIEW_WIDTH:
        scaled_height = round(height * MAX_PREVIEW_WIDTH / width)
        frame = cv2.resize(frame, (MAX_PREVIEW_WIDTH, scaled_height))
    encoded, buffer = cv2.imencode(
        ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 78]
    )
    if not encoded:
        raise VideoProcessingError("Could not encode the annotated preview frame.")
    return base64.b64encode(buffer).decode("ascii")


def analyze_video(
    video_path: Path,
    config: DetectionConfig,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        capture.release()
        raise VideoProcessingError(
            "OpenCV could not read this video. Try a supported MP4, MOV, AVI, MKV, or WebM file."
        )

    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        reported_frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if (
            not math.isfinite(fps)
            or not math.isfinite(reported_frames)
            or fps <= 0
            or reported_frames <= 0
        ):
            raise VideoProcessingError(
                "The video does not contain readable frame-rate or duration metadata."
            )

        width = capture.get(cv2.CAP_PROP_FRAME_WIDTH)
        height = capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
        if (
            not math.isfinite(width)
            or not math.isfinite(height)
            or width <= 0
            or height <= 0
            or width * height > MAX_FRAME_PIXELS
        ):
            raise VideoProcessingError(
                "Video frame dimensions are unsupported or exceed the 16-megapixel limit."
            )

        duration = reported_frames / fps
        if duration > MAX_VIDEO_SECONDS:
            raise VideoProcessingError(
                f"Video duration exceeds the {MAX_VIDEO_SECONDS}-second limit."
            )

        frame_interval = max(1, round(fps / INFERENCE_FPS))
        model = get_model()
        frame_index = 0
        sampled_frames = 0
        person_detections = 0
        entry_cooldown = RegionEntryCooldown(config.cooldown_seconds)
        entry_events: list[dict[str, Any]] = []
        preview_base64: str | None = None

        while True:
            if cancel_event and cancel_event.is_set():
                raise VideoProcessingCancelled
            if frame_index / fps > MAX_VIDEO_SECONDS:
                raise VideoProcessingError(
                    f"Video duration exceeds the {MAX_VIDEO_SECONDS}-second limit."
                )
            success, frame = capture.read()
            if not success:
                break

            if frame_index % frame_interval == 0:
                if frame.shape[0] * frame.shape[1] > MAX_FRAME_PIXELS:
                    raise VideoProcessingError(
                        "A decoded frame exceeds the 16-megapixel processing limit."
                    )
                media_time = frame_index / fps
                height, width = frame.shape[:2]
                roi_left = config.roi_x * width
                roi_top = config.roi_y * height
                roi_right = (config.roi_x + config.roi_width) * width
                roi_bottom = (config.roi_y + config.roi_height) * height
                current_detections: list[dict[str, float | int]] = []
                in_region_confidences: list[float] = []

                with _model_lock:
                    result = model.predict(
                        source=frame,
                        classes=[0],
                        conf=config.confidence,
                        verbose=False,
                    )[0]

                if result.boxes is not None:
                    for box in result.boxes:
                        coordinates = box.xyxy[0].tolist()
                        confidence = float(box.conf[0].item())
                        detection = {
                            "x1": round(coordinates[0]),
                            "y1": round(coordinates[1]),
                            "x2": round(coordinates[2]),
                            "y2": round(coordinates[3]),
                            "confidence": confidence,
                        }
                        current_detections.append(detection)
                        center_x = (coordinates[0] + coordinates[2]) / 2
                        center_y = (coordinates[1] + coordinates[3]) / 2
                        if (
                            roi_left <= center_x <= roi_right
                            and roi_top <= center_y <= roi_bottom
                        ):
                            in_region_confidences.append(confidence)

                person_detections += len(current_detections)
                occupied = bool(in_region_confidences)
                entry_confidence = entry_cooldown.observe(
                    occupied,
                    max(in_region_confidences) if in_region_confidences else None,
                    media_time,
                )
                if entry_confidence is not None:
                    entry_events.append(
                        {
                            "media_time_seconds": round(media_time, 2),
                            "confidence": entry_confidence,
                            "alert_message": (
                                "Home security alert. A person has been detected in "
                                "the monitored area. "
                                "Please check the security dashboard."
                            ),
                        }
                    )
                annotated = _annotate(frame, current_detections, config)
                preview_base64 = _encode_preview(annotated)
                sampled_frames += 1
            frame_index += 1

        if sampled_frames == 0:
            raise VideoProcessingError("No video frames could be decoded.")

        return {
            "duration_seconds": round(duration, 2),
            "sampled_frames": sampled_frames,
            "person_detections": person_detections,
            "region_entry_events": entry_events,
            "roi": {
                "x": config.roi_x,
                "y": config.roi_y,
                "width": config.roi_width,
                "height": config.roi_height,
            },
            "annotated_frame_jpeg": preview_base64,
        }
    finally:
        capture.release()
