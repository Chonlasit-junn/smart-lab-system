"""Reproducible synthetic Gatekeeper measurements; never connects to a real DB/camera."""

import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def kiosk():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import queue
    import numpy as np

    sys.path.insert(0, str(ROOT / "gatekeeper"))
    import smart_gatekeeper as app
    import access_client

    # Exercise the real preview loop without a Tk window or native image handles.
    frames = queue.Queue()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    instance = SimpleNamespace(
        _frame_queue=frames, models_loaded=False, video_label=Mock(), after=Mock(),
        _display_loop=Mock(), _stop_event=threading.Event(), _preview_image=None,
        _camera_generation=0, _last_faces=[],
        _remember_camera=Mock(),
    )
    if hasattr(app, "CameraStream"):
        instance._camera = SimpleNamespace(snapshot=lambda: SimpleNamespace(
            frame=frame, generation=0, sequence=instance.sequence,
        ))
        instance._preview_sequence = None
        instance._sync_camera = Mock()
    elapsed = []
    with patch.object(app.ctk, "CTkImage") as images, patch.object(
        app.Image, "fromarray", wraps=app.Image.fromarray,
    ) as pil:
        for i in range(250):
            instance.sequence = i
            if not hasattr(app, "CameraStream"):
                frames.put(frame.copy())
            started = time.perf_counter()
            app.GatekeeperDemo._display_loop(instance)
            elapsed.append((time.perf_counter() - started) * 1000)
        preview = {"frames": 250, "ctk_image_objects": images.call_count,
                   "pil_images": pil.call_count, "median_preparation_ms": statistics.median(elapsed)}

    class Camera:
        def __init__(self, index, *_args):
            time.sleep(0.02)  # deterministic simulated camera-driver open latency
            self.index = index
        def isOpened(self): return self.index == 0
        def release(self): pass
        def set(self, *_args): pass
        def read(self):
            time.sleep(0.01)
            return True, frame.copy()

    with patch.object(app.cv2, "VideoCapture", Camera):
        started = time.perf_counter()
        if hasattr(app, "CameraStream"):
            camera = app.CameraStream(0)
            camera.start()
            startup_ms = (time.perf_counter() - started) * 1000
            camera.stop()
            camera.join(1)
        else:
            app.GatekeeperDemo._scan_cameras(None)
            startup_ms = (time.perf_counter() - started) * 1000

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        connections = 0
        def get_request(self):
            result = super().get_request()
            self.connections += 1
            return result

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            body = b'{"access_granted":true,"scan_id":1,"user_name":"Synthetic User"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_args): pass

    server = Server(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    transport = access_client.ScanClient() if hasattr(access_client, "ScanClient") else None
    registration = {"device_id": "gatekeeper-benchmark", "device_token": "synthetic"}
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        for _ in range(8):
            kwargs = {"client": transport.session} if transport else {}
            accepted, _ = access_client.verify_scan(url, registration, frame, 0.9, **kwargs)
            assert accepted
        connections = server.connections
    finally:
        if transport:
            transport.close()
        server.shutdown()
        server.server_close()
    return {"preview": preview, "ui_camera_start_ms": startup_ms,
            "http_requests": 8, "http_tcp_connections": connections}


def backend():
    os.environ["SQLALCHEMY_DATABASE_URL"] = "sqlite:///:memory:"
    sys.path.insert(0, str(ROOT / "backend" / "tests"))
    from sqlalchemy import event
    from test_gatekeeper_access import GatekeeperAccessTests

    case = GatekeeperAccessTests()
    case.setUp()
    active = {"connections": 0}
    def checkout(*_args): active["connections"] += 1
    def checkin(*_args): active["connections"] -= 1
    event.listen(case.engine, "checkout", checkout)
    event.listen(case.engine, "checkin", checkin)
    measurements = []
    def inference(**_kwargs):
        started = time.perf_counter()
        held = active["connections"] > 0
        time.sleep(0.05)
        measurements.append({"db_connection_held": held,
                             "inference_ms": (time.perf_counter() - started) * 1000})
        return [{"embedding": [1.0, 0.0, 0.0]}]
    case.model.represent.side_effect = inference
    try:
        for _ in range(8):
            assert case.identify().status_code == 200
        assert len(case.scans()) == 8
        return {"scans": 8, "mock_inference_ms": 50,
                "inferences_holding_db": sum(row["db_connection_held"] for row in measurements),
                "db_hold_during_inference_ms": sum(
                    row["inference_ms"] for row in measurements if row["db_connection_held"]),
                "audit_rows": len(case.scans())}
    finally:
        case.tearDown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part", choices=("kiosk", "backend"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = {"scope": "synthetic; no real camera, database, face data or production traffic",
              "part": args.part, "metrics": globals()[args.part]()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
