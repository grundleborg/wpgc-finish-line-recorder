import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app


class DummyProcess:
    def __init__(self) -> None:
        self._running = True

    def poll(self):
        return None if self._running else 0

    def send_signal(self, _signal):
        self._running = False

    def wait(self, timeout=None):
        self._running = False
        return 0


class AppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        app = create_app(
            {
                "TESTING": True,
                "CAMERA_URL": "rtsp://example.invalid/camera",
                "RECORDINGS_DIR": Path(self.tmpdir.name),
            }
        )
        self.client = app.test_client()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    @patch("subprocess.Popen", return_value=DummyProcess())
    def test_start_and_stop_recording(self, _popen) -> None:
        start = self.client.post("/api/start")
        self.assertEqual(start.status_code, 200)
        self.assertTrue(start.get_json()["started"])

        status = self.client.get("/api/status")
        self.assertTrue(status.get_json()["recording"])

        stop = self.client.post("/api/stop")
        self.assertEqual(stop.status_code, 200)
        self.assertTrue(stop.get_json()["stopped"])

    @patch("subprocess.Popen", side_effect=FileNotFoundError("ffmpeg not found"))
    def test_start_handles_missing_ffmpeg(self, _popen) -> None:
        response = self.client.post("/api/start")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertFalse(payload["started"])
        self.assertIn("error", payload)

    def test_recordings_endpoint_lists_files(self) -> None:
        (Path(self.tmpdir.name) / "recording-1.mkv").write_bytes(b"abc")
        (Path(self.tmpdir.name) / "recording-2.mkv").write_bytes(b"abcd")

        response = self.client.get("/api/recordings")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(len(payload["recordings"]), 2)
        self.assertEqual(payload["recordings"][0]["name"], "recording-2.mkv")


if __name__ == "__main__":
    unittest.main()
