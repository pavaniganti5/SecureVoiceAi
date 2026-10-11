import base64
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app import main, murf_service
from test_alert_history import FakeCollection


class MurfServiceTests(unittest.TestCase):
    def test_sends_official_generation_payload_and_decodes_audio(self) -> None:
        audio = b"test-mp3-audio"
        request_details: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            request_details["url"] = str(request.url)
            request_details["headers"] = request.headers
            request_details["json"] = request.read()
            return httpx.Response(
                200,
                json={"encodedAudio": base64.b64encode(audio).decode("ascii")},
            )

        speech = murf_service.generate_speech(
            "A person entered the monitored area.",
            api_key="test-api-key",
            transport=httpx.MockTransport(handler),
        )

        self.assertEqual(request_details["url"], murf_service.MURF_GENERATE_URL)
        headers = request_details["headers"]
        self.assertEqual(headers["api-key"], "test-api-key")
        payload = json.loads(request_details["json"])
        self.assertEqual(payload["text"], "A person entered the monitored area.")
        self.assertEqual(payload["modelVersion"], "GEN2")
        self.assertEqual(payload["format"], "MP3")
        self.assertTrue(payload["encodeAsBase64"])
        self.assertEqual(base64.b64decode(speech.audio_base64), audio)
        self.assertEqual(speech.audio_content_type, "audio/mpeg")

    def test_missing_api_key_fails_without_network_request(self) -> None:
        with patch.dict(os.environ, {"MURF_API_KEY": ""}):
            with self.assertRaisesRegex(
                murf_service.MurfServiceError, "MURF_API_KEY"
            ):
                murf_service.generate_speech("Test alert")

    def test_network_failure_returns_safe_error(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("test network failure")

        with self.assertRaisesRegex(
            murf_service.MurfServiceError, "could not be reached"
        ):
            murf_service.generate_speech(
                "Test alert",
                api_key="test-api-key",
                transport=httpx.MockTransport(handler),
            )

    def test_rate_limit_returns_safe_error(self) -> None:
        transport = httpx.MockTransport(
            lambda _: httpx.Response(429, json={"message": "private provider detail"})
        )
        with self.assertRaisesRegex(murf_service.MurfServiceError, "quota"):
            murf_service.generate_speech(
                "Test alert", api_key="test-api-key", transport=transport
            )


class DetectionVoiceRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.collection = FakeCollection()
        self.environment = patch.dict(
            os.environ,
            {
                "MONGODB_URI": "",
                "MURF_API_KEY": "",
            },
        )
        self.environment.start()
        self.collection_patch = patch.object(
            main.database,
            "_get_alerts_collection",
            return_value=self.collection,
        )
        self.collection_patch.start()
        self.client = TestClient(main.app)
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.collection_patch.stop()
        self.environment.stop()

    def _fake_analysis(self, *_: object) -> dict[str, object]:
        return {
            "duration_seconds": 1.0,
            "sampled_frames": 1,
            "person_detections": 1,
            "region_entry_events": [
                {
                    "media_time_seconds": 0.2,
                    "confidence": 0.91,
                    "alert_message": (
                        "A person was detected entering the monitored region. "
                        "Please check the security dashboard."
                    ),
                }
            ],
            "roi": {"x": 0, "y": 0, "width": 1, "height": 1},
            "annotated_frame_jpeg": None,
        }

    def _post_video(self) -> httpx.Response:
        return self.client.post(
            "/api/detection/video",
            headers={"X-Analysis-ID": str(uuid4())},
            files={"video": ("sample.mp4", b"not-needed-for-mocked-analysis", "video/mp4")},
        )

    def test_detection_event_generates_voice_and_playback_status_is_persisted(self) -> None:
        generated_audio = murf_service.GeneratedSpeech(
            audio_base64=base64.b64encode(b"fake-mp3").decode("ascii"),
            audio_content_type="audio/mpeg",
        )
        with (
            patch.object(main, "analyze_video", side_effect=self._fake_analysis),
            patch.object(
                main.murf_service, "generate_speech", return_value=generated_audio
            ) as generate,
        ):
            response = self._post_video()

        self.assertEqual(response.status_code, 200, response.text)
        event = response.json()["region_entry_events"][0]
        self.assertEqual(event["voice_generation_status"], "generated")
        self.assertEqual(event["audio_base64"], generated_audio.audio_base64)
        generate.assert_called_once_with(event["alert_message"])

        playback = self.client.post(
            f"/api/alerts/{event['event_id']}/playback",
            json={"status": "played"},
        )
        self.assertEqual(playback.status_code, 200, playback.text)
        stored_alerts = self.client.get("/api/alerts").json()["items"]
        self.assertEqual(stored_alerts[0]["voice_generation_status"], "generated")
        self.assertEqual(stored_alerts[0]["playback_status"], "played")

    def test_murf_failure_does_not_discard_detection_event(self) -> None:
        with (
            patch.object(main, "analyze_video", side_effect=self._fake_analysis),
            patch.object(
                main.murf_service,
                "generate_speech",
                side_effect=murf_service.MurfServiceError("Murf API key is not configured."),
            ),
        ):
            response = self._post_video()

        self.assertEqual(response.status_code, 200, response.text)
        event = response.json()["region_entry_events"][0]
        self.assertEqual(event["voice_generation_status"], "failed")
        self.assertIn("API key is not configured", event["voice_error"])
        alert = self.client.get("/api/alerts").json()["items"][0]
        self.assertEqual(alert["event_type"], "person_entered_roi")
        self.assertEqual(alert["detection_status"], "detected")
        self.assertEqual(alert["source"], "uploaded_video")
        self.assertEqual(alert["voice_generation_status"], "failed")

    def test_missing_key_marks_detection_failed_without_calling_murf(self) -> None:
        with patch.object(main, "analyze_video", side_effect=self._fake_analysis):
            response = self._post_video()

        self.assertEqual(response.status_code, 200, response.text)
        event = response.json()["region_entry_events"][0]
        self.assertEqual(event["voice_generation_status"], "failed")
        self.assertIn("API key is not configured", event["voice_error"])
        self.assertIsNone(event["audio_base64"])
        alert = self.client.get("/api/alerts").json()["items"][0]
        self.assertEqual(alert["voice_generation_status"], "failed")

    def test_voice_status_does_not_expose_api_key(self) -> None:
        response = self.client.get("/api/voice/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"configured": False, "voice_id": "en-US-natalie", "model": "GEN2"},
        )

    def test_get_sample_video_returns_video_file(self) -> None:
        response = self.client.get("/api/detection/sample-video")
        self.assertEqual(response.status_code, 200)
        self.assertIn("video/", response.headers.get("content-type", ""))
        self.assertGreater(len(response.content), 1000)


if __name__ == "__main__":
    unittest.main()
