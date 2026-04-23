from __future__ import annotations

import os
import signal
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from flask import Flask, Response, abort, jsonify, render_template, send_from_directory
from werkzeug.utils import safe_join


class RecorderController:
    def __init__(self, camera_url: str, recordings_dir: Path) -> None:
        self._camera_url = camera_url
        self._recordings_dir = recordings_dir
        self._recordings_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._current_filename: str | None = None
        self._last_error: str = ""

    def start(self) -> dict[str, str | bool]:
        with self._lock:
            if self._is_process_running():
                return {"started": False, "filename": self._current_filename or ""}

            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"recording-{timestamp}.mkv"
            output_path = self._recordings_dir / filename

            cmd = [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-rtsp_transport",
                "tcp",
                "-i",
                self._camera_url,
                "-map",
                "0",
                "-c",
                "copy",
                "-f",
                "matroska",
                str(output_path),
            ]
            try:
                self._process = subprocess.Popen(cmd)
            except FileNotFoundError:
                self._last_error = "ffmpeg is not available on the system"
                return {"started": False, "filename": "", "error": self._last_error}
            except OSError:
                self._last_error = "failed to start ffmpeg"
                return {"started": False, "filename": "", "error": self._last_error}
            self._current_filename = filename
            self._last_error = ""
            return {"started": True, "filename": filename}

    def stop(self) -> dict[str, str | bool]:
        with self._lock:
            process = self._process
            filename = self._current_filename
            if process is None or process.poll() is not None:
                self._process = None
                self._current_filename = None
                return {"stopped": False, "filename": ""}

            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass

            self._process = None
            self._current_filename = None
            return {"stopped": True, "filename": filename or ""}

    def status(self) -> dict[str, str | bool]:
        with self._lock:
            recording = self._is_process_running()
            if not recording:
                self._process = None
                self._current_filename = None
            return {
                "recording": recording,
                "filename": self._current_filename or "",
                "error": self._last_error,
            }

    def recordings(self) -> list[dict[str, int | str]]:
        entries = []
        for path in sorted(self._recordings_dir.glob("*.mkv"), reverse=True):
            if path.is_file():
                entries.append({"name": path.name, "size": path.stat().st_size})
        return entries

    def _is_process_running(self) -> bool:
        return self._process is not None and self._process.poll() is None


BOUNDARY = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"


def _stream_preview(camera_url: str) -> Iterator[bytes]:
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-i",
        camera_url,
        "-vf",
        "fps=2,scale=640:-1",
        "-f",
        "image2pipe",
        "-vcodec",
        "mjpeg",
        "pipe:1",
    ]

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        return
    if process.stdout is None:
        return

    try:
        buffer = bytearray()
        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                break
            buffer.extend(chunk)

            while True:
                start = buffer.find(b"\xff\xd8")
                end = buffer.find(b"\xff\xd9", start + 2 if start != -1 else 0)
                if start == -1 or end == -1:
                    break

                frame = bytes(buffer[start : end + 2])
                del buffer[: end + 2]
                yield BOUNDARY + frame + b"\r\n"
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()


def create_app(test_config: dict[str, object] | None = None) -> Flask:
    app = Flask(__name__)

    app.config.update(
        CAMERA_URL=os.getenv("CAMERA_URL", "rtsp://10.20.30.11"),
        RECORDINGS_DIR=Path(os.getenv("RECORDINGS_DIR", "recordings")),
    )

    if test_config:
        app.config.update(test_config)

    controller = RecorderController(
        camera_url=str(app.config["CAMERA_URL"]),
        recordings_dir=Path(app.config["RECORDINGS_DIR"]),
    )
    app.config["RECORDER_CONTROLLER"] = controller

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/status")
    def status() -> Response:
        return jsonify(controller.status())

    @app.post("/api/start")
    def start() -> Response:
        return jsonify(controller.start())

    @app.post("/api/stop")
    def stop() -> Response:
        return jsonify(controller.stop())

    @app.get("/api/recordings")
    def recordings() -> Response:
        return jsonify({"recordings": controller.recordings()})

    @app.get("/api/recordings/<path:filename>")
    def download(filename: str) -> Response:
        if safe_join(app.config["RECORDINGS_DIR"], filename) is None:
            abort(404)
        return send_from_directory(app.config["RECORDINGS_DIR"], filename, as_attachment=True)

    @app.get("/preview.mjpg")
    def preview() -> Response:
        return Response(
            _stream_preview(str(app.config["CAMERA_URL"])),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
