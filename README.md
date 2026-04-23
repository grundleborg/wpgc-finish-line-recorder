# wpgc-finish-line-recorder

Lightweight Raspberry Pi-friendly RTSP recorder for the WPGC finish line camera.

## Features

- Start/stop recording over a simple web UI
- Recording state API (`/api/status`)
- Recording list/download API (`/api/recordings`)
- Live preview in the UI (`/preview.mjpg`)
- Recording with stream copy (`ffmpeg -c copy`) to avoid transcoding recorded output

## Requirements

- Raspberry Pi OS (Pi 5 target)
- Python 3.11+
- `ffmpeg`

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
CAMERA_URL="rtsp://10.20.30.11" RECORDINGS_DIR="./recordings" python3 app.py
```

Then open `http://<pi-ip>:8080`.

## API

- `GET /api/status` → current state
- `POST /api/start` → start recording
- `POST /api/stop` → stop recording
- `GET /api/recordings` → list files
- `GET /api/recordings/<filename>` → download a file

## Auto-start on Raspberry Pi

1. Copy project to `/opt/wpgc-finish-line-recorder`
2. Install dependencies:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-pip ffmpeg
   sudo python3 -m pip install -r /opt/wpgc-finish-line-recorder/requirements.txt
   sudo mkdir -p /var/lib/wpgc-recordings
   sudo chown pi:pi /var/lib/wpgc-recordings
   ```
3. Install service:
   ```bash
   sudo cp /opt/wpgc-finish-line-recorder/systemd/wpgc-finish-line-recorder.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now wpgc-finish-line-recorder.service
   ```
4. Check status:
   ```bash
   systemctl status wpgc-finish-line-recorder.service
   ```

The provided service is configured with restart-on-failure for reliability.
