#!/usr/bin/env python3
"""Local-only control panel for the usb-power CLI."""

import argparse
import json
import secrets
import subprocess
import threading
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
            [SCRIPT, *args], capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return result.returncode == 0, (result.stdout or result.stderr).strip()


def snapshot() -> dict:
    ports = {}
    for port in ("1", "2"):
        ok, power = run_cli("status", port)
        cycle_ok, cycle = run_cli("cycle", "status", port)
        ports[port] = {
            "power": power.rsplit(" ", 1)[-1] if ok else "unknown",
            "cycle": "enabled" if cycle_ok and "cycle enabled" in cycle else "disabled",
            "error": "" if ok and cycle_ok else power or cycle,
        }
    _, hub = run_cli("hub")
    return {"hub": hub.removeprefix("Hub: "), "ports": ports}


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
