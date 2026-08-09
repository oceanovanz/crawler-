#!/usr/bin/env python3
"""
Oceanova crawler USB-camera and ESP32 telemetry server.

Serves:
  /                 Browser dashboard
  /stream.mjpg      Low-latency MJPEG stream
  /snapshot.jpg     Latest still image
  /telemetry.json   Latest ESP32 serial telemetry
  /health           Camera/server/serial status

Example:
  python3 crawler_stream.py --camera 0 --width 1280 --height 720 \
      --fps 20 --serial auto --port 8080
"""

from __future__ import annotations

import argparse
import glob
import html
import json
import logging
import signal
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional
from urllib.parse import urlparse

try:
    import cv2
except ImportError as exc:
    raise SystemExit(
        "OpenCV is required. Install it with:\n"
        "  sudo apt update && sudo apt install -y python3-opencv"
    ) from exc

try:
    import serial  # type: ignore
except ImportError:
    serial = None

LOG = logging.getLogger("crawler-stream")


@dataclass
class SharedState:
    frame_condition: threading.Condition = field(
        default_factory=lambda: threading.Condition(threading.Lock())
    )
    latest_jpeg: Optional[bytes] = None
    frame_sequence: int = 0
    frame_timestamp: float = 0.0
    status_lock: threading.Lock = field(default_factory=threading.Lock)
    camera_ok: bool = False
    camera_error: str = "Camera has not started"
    actual_width: int = 0
    actual_height: int = 0
    actual_fps: float = 0.0
    serial_ok: bool = False
    serial_port: Optional[str] = None
    serial_error: str = "Serial telemetry disabled"
    telemetry_raw: str = ""
    telemetry_timestamp: float = 0.0
    telemetry: dict[str, Any] = field(default_factory=dict)
    start_monotonic: float = field(default_factory=time.monotonic)

    def publish_frame(self, jpeg: bytes) -> None:
        with self.frame_condition:
            self.latest_jpeg = jpeg
            self.frame_sequence += 1
            self.frame_timestamp = time.time()
            self.frame_condition.notify_all()

    def set_camera_status(self, ok: bool, error: str = "", width: int = 0, height: int = 0, fps: float = 0.0) -> None:
        with self.status_lock:
            self.camera_ok = ok
            self.camera_error = error
            if width:
                self.actual_width = width
            if height:
                self.actual_height = height
            if fps:
                self.actual_fps = fps

    def set_serial_status(self, ok: bool, port: Optional[str] = None, error: str = "") -> None:
        with self.status_lock:
            self.serial_ok = ok
            self.serial_port = port
            self.serial_error = error

    def publish_telemetry(self, raw: str, parsed: dict[str, Any]) -> None:
        with self.status_lock:
            self.telemetry_raw = raw
            self.telemetry_timestamp = time.time()
            self.telemetry = parsed

    def snapshot(self) -> dict[str, Any]:
        now = time.time()
        with self.status_lock:
            telemetry_age = now - self.telemetry_timestamp if self.telemetry_timestamp else None
            frame_age = now - self.frame_timestamp if self.frame_timestamp else None
            return {
                "server": {"uptime_s": round(time.monotonic() - self.start_monotonic, 1), "time_unix": now},
                "camera": {
                    "ok": self.camera_ok,
                    "error": self.camera_error,
                    "width": self.actual_width,
                    "height": self.actual_height,
                    "fps_requested_or_reported": round(self.actual_fps, 2),
                    "frame_sequence": self.frame_sequence,
                    "last_frame_age_s": round(frame_age, 3) if frame_age is not None else None,
                },
                "serial": {
                    "ok": self.serial_ok,
                    "port": self.serial_port,
                    "error": self.serial_error,
                    "last_line_age_s": round(telemetry_age, 3) if telemetry_age is not None else None,
                },
                "telemetry": self.telemetry,
                "telemetry_raw": self.telemetry_raw,
            }


class CameraWorker(threading.Thread):
    def __init__(self, state: SharedState, stop_event: threading.Event, camera_index: int, width: int, height: int, fps: int, jpeg_quality: int, rotate: int) -> None:
        super().__init__(name="camera", daemon=True)
        self.state = state
        self.stop_event = stop_event
        self.camera_index = camera_index
        self.width = width
        self.height = height
        self.fps = fps
        self.jpeg_quality = jpeg_quality
        self.rotate = rotate

    def _open_camera(self):
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = float(cap.get(cv2.CAP_PROP_FPS)) or float(self.fps)
        self.state.set_camera_status(True, "", width=actual_width, height=actual_height, fps=actual_fps)
        LOG.info("USB camera opened: /dev/video%d, %dx%d at %.1f fps", self.camera_index, actual_width, actual_height, actual_fps)
        return cap

    def _rotate_frame(self, frame):
        if self.rotate == 90:
            return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        if self.rotate == 180:
            return cv2.rotate(frame, cv2.ROTATE_180)
        if self.rotate == 270:
            return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return frame

    def run(self) -> None:
        cap = None
        consecutive_failures = 0
        while not self.stop_event.is_set():
            if cap is None:
                cap = self._open_camera()
                if cap is None:
                    message = f"Could not open camera index {self.camera_index}; retrying in 2 seconds"
                    self.state.set_camera_status(False, message)
                    LOG.error(message)
                    self.stop_event.wait(2.0)
                    continue
            ok, frame = cap.read()
            if not ok or frame is None:
                consecutive_failures += 1
                self.state.set_camera_status(False, f"Camera frame read failed ({consecutive_failures})")
                if consecutive_failures >= 10:
                    LOG.warning("Reopening camera after repeated read failures")
                    cap.release()
                    cap = None
                    consecutive_failures = 0
                    self.stop_event.wait(0.5)
                else:
                    self.stop_event.wait(0.05)
                continue
            consecutive_failures = 0
            frame = self._rotate_frame(frame)
            encode_ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
            if not encode_ok:
                self.state.set_camera_status(False, "JPEG encoding failed")
                continue
            self.state.set_camera_status(True, "")
            self.state.publish_frame(encoded.tobytes())
        if cap is not None:
            cap.release()


def parse_esp32_line(line: str) -> dict[str, Any]:
    fields = [field.strip() for field in line.split(",")]
    if len(fields) == 10 and fields[0] == "T":
        try:
            return {
                "type": "orientation",
                "esp32_time_ms": int(fields[1]),
                "yaw_deg": float(fields[2]),
                "pitch_deg": float(fields[3]),
                "roll_deg": float(fields[4]),
                "left_output": int(fields[5]),
                "right_output": int(fields[6]),
                "armed": bool(int(fields[7])),
                "imu_online": bool(int(fields[8])),
                "orientation_valid": bool(int(fields[9])),
            }
        except ValueError:
            pass
    return {"type": "text", "line": line}


def serial_candidates(requested_port: str) -> list[str]:
    if requested_port != "auto":
        return [requested_port]
    candidates: list[str] = []
    for pattern in ("/dev/serial/by-id/*", "/dev/ttyACM*", "/dev/ttyUSB*"):
        candidates.extend(sorted(glob.glob(pattern)))
    return list(dict.fromkeys(candidates))


class SerialWorker(threading.Thread):
    def __init__(self, state: SharedState, stop_event: threading.Event, requested_port: str, baud: int) -> None:
        super().__init__(name="serial", daemon=True)
        self.state = state
        self.stop_event = stop_event
        self.requested_port = requested_port
        self.baud = baud

    def run(self) -> None:
        if serial is None:
            message = "pySerial is not installed; video will run without ESP32 telemetry. Install python3-serial to enable it."
            self.state.set_serial_status(False, error=message)
            LOG.warning(message)
            return
        while not self.stop_event.is_set():
            ports = serial_candidates(self.requested_port)
            if not ports:
                message = "No ESP32 serial port found; retrying"
                self.state.set_serial_status(False, error=message)
                self.stop_event.wait(2.0)
                continue
            connection = None
            connected_port = None
            last_error = ""
            for port in ports:
                try:
                    connection = serial.Serial(port=port, baudrate=self.baud, timeout=0.25, write_timeout=0.5, rtscts=False, dsrdtr=False)
                    connection.dtr = False
                    connection.rts = False
                    connection.reset_input_buffer()
                    connected_port = port
                    break
                except Exception as exc:
                    last_error = f"{port}: {exc}"
            if connection is None or connected_port is None:
                self.state.set_serial_status(False, error=last_error or "Open failed")
                self.stop_event.wait(2.0)
                continue
            self.state.set_serial_status(True, port=connected_port, error="")
            LOG.info("ESP32 telemetry connected on %s at %d baud", connected_port, self.baud)
            try:
                while not self.stop_event.is_set():
                    payload = connection.readline()
                    if not payload:
                        continue
                    line = payload.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    self.state.publish_telemetry(line, parse_esp32_line(line))
            except Exception as exc:
                message = f"Serial disconnected: {exc}"
                self.state.set_serial_status(False, port=connected_port, error=message)
                LOG.warning(message)
            finally:
                try:
                    connection.close()
                except Exception:
                    pass
            self.stop_event.wait(1.0)


def build_dashboard(title: str) -> bytes:
    safe_title = html.escape(title)
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{safe_title}</title>
  <style>
    :root {{ color-scheme: dark; font-family: system-ui, sans-serif; }}
    body {{ margin: 0; background: #101418; color: #eef3f7; }}
    header {{ display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: .7rem 1rem; background: #1a2229; position: sticky; top: 0; z-index: 1; }}
    h1 {{ font-size: 1.05rem; margin: 0; }}
    #status {{ font-weight: 700; }}
    main {{ display: grid; grid-template-columns: minmax(0, 3fr) minmax(260px, 1fr); gap: .75rem; padding: .75rem; }}
    .panel {{ background: #182027; border-radius: .6rem; overflow: hidden; }}
    #video {{ display: block; width: 100%; height: auto; min-height: 240px; object-fit: contain; background: #000; }}
    .telemetry {{ padding: 1rem; }}
    .grid {{ display: grid; grid-template-columns: 1fr auto; gap: .55rem 1rem; font-variant-numeric: tabular-nums; }}
    .label {{ opacity: .7; }}
    .value {{ font-weight: 700; text-align: right; }}
    #raw {{ margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #34414b; overflow-wrap: anywhere; font-family: ui-monospace, monospace; font-size: .8rem; opacity: .8; }}
    .ok {{ color: #7ee787; }}
    .bad {{ color: #ff7b72; }}
    @media (max-width: 850px) {{ main {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header><h1>{safe_title}</h1><div id="status">Connecting…</div></header>
  <main>
    <section class="panel"><img id="video" src="/stream.mjpg" alt="Crawler camera stream"></section>
    <section class="panel telemetry">
      <div class="grid">
        <span class="label">Camera</span><span class="value" id="camera">—</span>
        <span class="label">ESP32 serial</span><span class="value" id="serial">—</span>
        <span class="label">Yaw</span><span class="value" id="yaw">—</span>
        <span class="label">Pitch</span><span class="value" id="pitch">—</span>
        <span class="label">Roll</span><span class="value" id="roll">—</span>
        <span class="label">Left output</span><span class="value" id="left">—</span>
        <span class="label">Right output</span><span class="value" id="right">—</span>
        <span class="label">Armed</span><span class="value" id="armed">—</span>
        <span class="label">IMU</span><span class="value" id="imu">—</span>
      </div>
      <div id="raw">Waiting for telemetry…</div>
    </section>
  </main>
<script>
const text = (id, value) => document.getElementById(id).textContent = value;
const stateClass = (id, ok) => {{ const node = document.getElementById(id); node.className = "value " + (ok ? "ok" : "bad"); }};
async function updateTelemetry() {{
  try {{
    const response = await fetch("/telemetry.json", {{cache: "no-store"}});
    const data = await response.json();
    const cameraFresh = data.camera.ok && data.camera.last_frame_age_s !== null && data.camera.last_frame_age_s < 2;
    const serialFresh = data.serial.ok && data.serial.last_line_age_s !== null && data.serial.last_line_age_s < 2;
    text("camera", cameraFresh ? "ONLINE" : "OFFLINE"); stateClass("camera", cameraFresh);
    text("serial", serialFresh ? "ONLINE" : "OFFLINE"); stateClass("serial", serialFresh);
    const t = data.telemetry || {{}};
    text("yaw", Number.isFinite(t.yaw_deg) ? t.yaw_deg.toFixed(1) + "°" : "—");
    text("pitch", Number.isFinite(t.pitch_deg) ? t.pitch_deg.toFixed(1) + "°" : "—");
    text("roll", Number.isFinite(t.roll_deg) ? t.roll_deg.toFixed(1) + "°" : "—");
    text("left", Number.isFinite(t.left_output) ? t.left_output : "—");
    text("right", Number.isFinite(t.right_output) ? t.right_output : "—");
    text("armed", typeof t.armed === "boolean" ? (t.armed ? "YES" : "NO") : "—");
    text("imu", typeof t.imu_online === "boolean" ? (t.imu_online ? "ONLINE" : "OFFLINE") : "—");
    text("raw", data.telemetry_raw || data.serial.error || "Waiting for telemetry…");
    text("status", cameraFresh ? "VIDEO ONLINE" : "VIDEO OFFLINE");
    document.getElementById("status").className = cameraFresh ? "ok" : "bad";
  }} catch (error) {{
    text("status", "SERVER DISCONNECTED");
    document.getElementById("status").className = "bad";
  }}
}}
setInterval(updateTelemetry, 250);
updateTelemetry();
</script>
</body>
</html>
"""
    return page.encode("utf-8")


class CrawlerHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, handler_class, state: SharedState, dashboard: bytes):
        super().__init__(server_address, handler_class)
        self.state = state
        self.dashboard = dashboard


class RequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "OceanovaCrawler/1.0"

    @property
    def crawler_server(self) -> CrawlerHTTPServer:
        return self.server  # type: ignore[return-value]

    def _send_bytes(self, status: int, content_type: str, payload: bytes, extra_headers: Optional[dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Connection", "close")
        if extra_headers:
            for name, value in extra_headers.items():
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, status: int, value: Any) -> None:
        payload = json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self._send_bytes(status, "application/json; charset=utf-8", payload)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_bytes(200, "text/html; charset=utf-8", self.crawler_server.dashboard)
            return
        if path == "/telemetry.json" or path == "/health":
            self._send_json(200, self.crawler_server.state.snapshot())
            return
        if path == "/snapshot.jpg":
            with self.crawler_server.state.frame_condition:
                jpeg = self.crawler_server.state.latest_jpeg
            if jpeg is None:
                self._send_json(503, {"error": "No camera frame available"})
            else:
                self._send_bytes(200, "image/jpeg", jpeg)
            return
        if path == "/stream.mjpg":
            self._stream_mjpeg()
            return
        if path == "/favicon.ico":
            self._send_bytes(204, "image/x-icon", b"")
            return
        self._send_json(404, {"error": "Not found"})

    def _stream_mjpeg(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        state = self.crawler_server.state
        last_sequence = -1
        try:
            while True:
                with state.frame_condition:
                    state.frame_condition.wait_for(lambda: state.frame_sequence != last_sequence, timeout=1.0)
                    if state.latest_jpeg is None:
                        continue
                    jpeg = state.latest_jpeg
                    last_sequence = state.frame_sequence
                self.wfile.write(b"--FRAME\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii"))
                self.wfile.write(jpeg)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except OSError:
            pass

    def log_message(self, fmt: str, *args: Any) -> None:
        LOG.debug("%s - %s", self.client_address[0], fmt % args)


def available_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        for entry in socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET, type=socket.SOCK_STREAM):
            address = entry[4][0]
            if not address.startswith("127."):
                addresses.add(address)
    except OSError:
        pass
    return sorted(addresses)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve a USB-camera MJPEG stream and ESP32 telemetry.")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port")
    parser.add_argument("--camera", type=int, default=0, help="USB camera index")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=20)
    parser.add_argument("--jpeg-quality", type=int, default=75, choices=range(20, 96), metavar="20-95")
    parser.add_argument("--rotate", type=int, default=0, choices=(0, 90, 180, 270), help="Rotate camera image clockwise")
    parser.add_argument("--serial", default="auto", help="ESP32 port, 'auto', or 'off'")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--title", default="Oceanova Crawler", help="Dashboard title")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop_event = threading.Event()
    state = SharedState()
    camera = CameraWorker(state=state, stop_event=stop_event, camera_index=args.camera, width=args.width, height=args.height, fps=args.fps, jpeg_quality=args.jpeg_quality, rotate=args.rotate)
    camera.start()

    serial_worker = None
    if args.serial.lower() != "off":
        serial_worker = SerialWorker(state=state, stop_event=stop_event, requested_port=args.serial, baud=args.baud)
        serial_worker.start()

    dashboard = build_dashboard(args.title)
    server = CrawlerHTTPServer((args.host, args.port), RequestHandler, state=state, dashboard=dashboard)
    LOG.info("Crawler server listening on %s:%d", args.host, args.port)
    addresses = available_ipv4_addresses()
    if addresses:
        for address in addresses:
            LOG.info("Open on laptop: http://%s:%d/", address, args.port)
    else:
        LOG.info("Open on laptop: http://<raspberry-pi-ip>:%d/", args.port)

    def raise_keyboard_interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, raise_keyboard_interrupt)
    signal.signal(signal.SIGINT, raise_keyboard_interrupt)

    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        LOG.info("Stopping crawler server")
    finally:
        stop_event.set()
        server.server_close()
        camera.join(timeout=2.0)
        if serial_worker is not None:
            serial_worker.join(timeout=2.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
