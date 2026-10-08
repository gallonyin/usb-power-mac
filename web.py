#!/usr/bin/env python3
"""Local-only control panel for the usb-power CLI."""

import argparse
import json
import os
import re
import secrets
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


SCRIPT = str(Path(__file__).with_name("usb-power"))
TOKEN = secrets.token_urlsafe(32)
HTML = (Path(__file__).with_name("index.html")).read_text(encoding="utf-8")


def run_cli(*args: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [SCRIPT, *args], capture_output=True, text=True, timeout=20, check=False,
            env={**os.environ, "USB_POWER_SOURCE": "web"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return result.returncode == 0, (result.stdout or result.stderr).strip()


def read_history() -> dict:
    path = Path.home() / "Library/Application Support/usb-power/power-history.tsv"
    records = []
    cutoff = int(time.time()) - 30 * 86400
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    timestamp, port, before, after, source, hub = line.rstrip("\n").split("\t")
                    timestamp = int(timestamp)
                    if timestamp < cutoff or port not in ("1", "2") or before not in ("on", "off") or after not in ("on", "off"):
                        continue
                    records.append(dict(timestamp=timestamp, port=port, before=before, after=after, source=source, hub=hub))
                except (ValueError, TypeError):
                    continue
    except FileNotFoundError:
        pass
    except OSError:
        return {"records": [], "error": "无法读取历史记录，请检查日志文件权限。"}
    records.sort(key=lambda row: row["timestamp"], reverse=True)
    return {"records": records, "error": ""}


def parse_devices(output: str) -> dict:
    devices = {}
    for line in output.splitlines():
        match = re.match(r"\s*Port ([12]):\s+(.+)", line)
        if not match or not re.search(r"\bconnect\b", match[2]):
            continue
        descriptor = re.search(r"\[[0-9a-fA-F]{4}:[0-9a-fA-F]{4}(?:\s+([^\]]+))?\]", match[2])
        name = descriptor[1].strip() if descriptor and descriptor[1] else ""
        # Do not show a trailing hexadecimal USB serial number in the UI.
        name = re.sub(r"\s+[0-9a-fA-F]{8,}$", "", name)
        if name or match[1] not in devices:
            devices[match[1]] = name or "未知设备"
    return devices


def snapshot() -> dict:
    devices_ok, device_output = run_cli("devices")
    devices = parse_devices(device_output) if devices_ok else {}
    power_states = {}
    for line in device_output.splitlines() if devices_ok else []:
        match = re.match(r"\s*Port ([12]):\s+(.+)", line)
        if match and match[1] not in power_states:
            power_states[match[1]] = "off" if re.search(r"\boff\b", match[2]) else "on" if re.search(r"\bpower\b", match[2]) else "unknown"
    state_dir = Path.home() / "Library/Application Support/usb-power"
    ports = {}
    for port in ("1", "2"):
        ports[port] = {
            "power": power_states.get(port, "unknown"),
            "cycle": "enabled" if (state_dir / f"port-{port}.start").is_file() else "disabled",
            "device": devices.get(port),
            "error": "" if power_states.get(port) in ("on", "off") else "无法读取端口状态",
        }
    try:
        hub = (state_dir / "hub").read_text().strip()
    except FileNotFoundError:
        hub = "2-1"
    return {"hub": hub, "ports": ports, "history": read_history()}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/":
            body = HTML.replace("__CSRF_TOKEN__", TOKEN).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/status":
            self.send_json(200, snapshot())
        elif path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/action":
            self.send_json(404, {"error": "Not found"})
            return
        if self.headers.get("X-USB-Power-Token") != TOKEN:
            self.send_json(403, {"error": "Invalid request token"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024:
                raise ValueError("Invalid body size")
            payload = json.loads(self.rfile.read(length))
            port = str(payload["port"])
            action = payload["action"]
            mode = payload["mode"]
            if port not in ("1", "2") or action not in ("on", "off") or mode not in ("power", "cycle"):
                raise ValueError("Invalid command")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            self.send_json(400, {"error": "Invalid command"})
            return
        args = ("cycle", action, port) if mode == "cycle" else (action, port)
        ok, message = run_cli(*args)
        self.send_json(200 if ok else 500, {"ok": ok, "message": message, "status": snapshot()})

    def log_message(self, format: str, *args: object) -> None:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Local usb-power control panel")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"USB Power control panel: {url}", flush=True)
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
