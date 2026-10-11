import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import detection
from app.schemas import DetectionConfig


class FakeFrame:
    shape = (48, 64, 3)


class FakeCapture:
    def __init__(self, fps: float, frame_count: int) -> None:
        self.fps = fps
        self.frame_count = frame_count
        self.next_frame = 0
        self.released = False

    def isOpened(self) -> bool:
        return True

    def get(self, property_id: int) -> float:
        properties = {
            detection.cv2.CAP_PROP_FPS: self.fps,
            detection.cv2.CAP_PROP_FRAME_COUNT: self.frame_count,
            detection.cv2.CAP_PROP_FRAME_WIDTH: FakeFrame.shape[1],
            detection.cv2.CAP_PROP_FRAME_HEIGHT: FakeFrame.shape[0],
        }
        return properties[property_id]

    def read(self) -> tuple[bool, FakeFrame | None]:
        if self.next_frame >= self.frame_count:
            return False, None
        self.next_frame += 1
        return True, FakeFrame()

    def grab(self) -> bool:
        if self.next_frame >= self.frame_count:
            return False
        self.next_frame += 1
        return True

    def release(self) -> None:
        self.released = True


class FakeModel:
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []
        self.prediction_options: list[tuple[list[int], float, bool]] = []

    def predict(
        self,
        source: list[FakeFrame],
        classes: list[int],
        conf: float,
        verbose: bool,
    ) -> list[SimpleNamespace]:
        self.batch_sizes.append(len(source))
        self.prediction_options.append((classes, conf, verbose))
        return [SimpleNamespace(boxes=None) for _ in source]


class VideoAnalysisPerformanceTests(unittest.TestCase):
    def _analyze(
        self, fps: float, frame_count: int, inference_fps: int
    ) -> tuple[dict[str, object], list[int]]:
        capture = FakeCapture(fps, frame_count)
        model = FakeModel()
        with (
            patch.object(detection.cv2, "VideoCapture", return_value=capture),
            patch.object(detection, "get_model", return_value=model),
            patch.object(detection, "_annotate", side_effect=lambda frame, *_: frame),
            patch.object(detection, "_encode_preview", return_value="preview"),
        ):
            result = detection.analyze_video(
                Path("sample.mp4"),
                DetectionConfig(inference_fps=inference_fps),
            )
        self.assertTrue(capture.released)
        return result, model.batch_sizes

    def test_default_sampling_batches_frames_and_reports_processing_time(self) -> None:
        result, batch_sizes = self._analyze(
            fps=20, frame_count=40, inference_fps=2
        )

        self.assertEqual(result["sampled_frames"], 4)
        self.assertEqual(batch_sizes, [4])
        self.assertGreaterEqual(result["processing_time_seconds"], 0)

    def test_sampling_rate_does_not_exceed_requested_rate(self) -> None:
        result, batch_sizes = self._analyze(
            fps=25, frame_count=25, inference_fps=10
        )

        self.assertEqual(result["sampled_frames"], 9)
        self.assertEqual(batch_sizes, [4, 4, 1])


if __name__ == "__main__":
    unittest.main()
