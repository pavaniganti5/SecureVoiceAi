import base64
import math
import os
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2
from ultralytics import YOLO

from app.schemas import DetectionConfig

_LOCAL_MODEL_PATH = Path(__file__).resolve().parent.parent / "yolo11n.pt"
DEFAULT_MODEL = str(_LOCAL_MODEL_PATH) if _LOCAL_MODEL_PATH.is_file() else "yolo11n.pt"
DEFAULT_INFERENCE_FPS = 2
MAX_VIDEO_SECONDS = 120
MAX_FRAME_PIXELS = 16_000_000
MAX_PREVIEW_WIDTH = 960
INFERENCE_BATCH_SIZE = 4

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
    started_at = time.perf_counter()
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

        frame_interval = max(1, math.ceil(fps / config.inference_fps))
        model = get_model()
        frame_index = 0
        sampled_frames = 0
        person_detections = 0
        entry_cooldown = RegionEntryCooldown(config.cooldown_seconds)
        entry_events: list[dict[str, Any]] = []

        best_preview_frame: Any = None
        best_preview_detections: list[dict[str, float | int]] = []
        highest_conf: float = -1.0

        batch_frames: list[Any] = []
        batch_meta: list[tuple[int, float, int, int]] = []

        def _process_batch(
            frames_to_process: list[Any],
            meta_to_process: list[tuple[int, float, int, int]],
        ) -> None:
            nonlocal person_detections, highest_conf, best_preview_frame, best_preview_detections
            if not frames_to_process:
                return

            with _model_lock:
                results = model.predict(
                    source=frames_to_process,
                    classes=[0],
                    conf=config.confidence,
                    verbose=False,
                )

            if len(results) != len(frames_to_process):
                raise VideoProcessingError(
                    "The detection model returned an unexpected number of results."
                )

            for (frame, (_, media_time, h, w)), result in zip(
                zip(frames_to_process, meta_to_process), results
            ):
                roi_left = config.roi_x * w
                roi_top = config.roi_y * h
                roi_right = (config.roi_x + config.roi_width) * w
                roi_bottom = (config.roi_y + config.roi_height) * h
                current_detections: list[dict[str, float | int]] = []
                in_region_confidences: list[float] = []

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
                    # Prioritize frame where person entered ROI
                    best_preview_frame = frame
                    best_preview_detections = current_detections
                    highest_conf = 999.0
                elif current_detections and highest_conf < 999.0:
                    max_frame_conf = max(float(d["confidence"]) for d in current_detections)
                    if max_frame_conf > highest_conf:
                        highest_conf = max_frame_conf
                        best_preview_frame = frame
                        best_preview_detections = current_detections
                elif best_preview_frame is None:
                    best_preview_frame = frame
                    best_preview_detections = current_detections

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

            if frame.shape[0] * frame.shape[1] > MAX_FRAME_PIXELS:
                raise VideoProcessingError(
                    "A decoded frame exceeds the 16-megapixel processing limit."
                )

            media_time = frame_index / fps
            h, w = frame.shape[:2]
            batch_frames.append(frame)
            batch_meta.append((frame_index, media_time, h, w))
            sampled_frames += 1

            if len(batch_frames) >= INFERENCE_BATCH_SIZE:
                if cancel_event and cancel_event.is_set():
                    raise VideoProcessingCancelled
                _process_batch(batch_frames, batch_meta)
                batch_frames.clear()
                batch_meta.clear()

            # Skip non-sampled frames using grab()
            for _ in range(frame_interval - 1):
                if not capture.grab():
                    break
                frame_index += 1
            frame_index += 1

        if batch_frames:
            if cancel_event and cancel_event.is_set():
                raise VideoProcessingCancelled
            _process_batch(batch_frames, batch_meta)
            batch_frames.clear()
            batch_meta.clear()

        if sampled_frames == 0:
            raise VideoProcessingError("No video frames could be decoded.")

        preview_base64: str | None = None
        if best_preview_frame is not None:
            annotated = _annotate(best_preview_frame, best_preview_detections, config)
            preview_base64 = _encode_preview(annotated)

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
            "processing_time_seconds": round(time.perf_counter() - started_at, 2),
        }
    finally:
        capture.release()
