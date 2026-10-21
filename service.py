#!/usr/bin/env python3
"""Install and manage the native macOS background service."""
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path.home() / "Library/Application Support/usb-power"
APP = ROOT / "app"
AGENTS = Path.home() / "Library/LaunchAgents"
LABEL = "com.kun.usb-power.web"
DOMAIN = f"gui/{os.getuid()}"


def launch(*args, check=True):
    return subprocess.run(["/bin/launchctl", *args], check=check, capture_output=True, text=True)


def install():
    APP.mkdir(parents=True, exist_ok=True)
    AGENTS.mkdir(parents=True, exist_ok=True)
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    source = Path(__file__).resolve().parent
    for name in ("usb-power", "web.py", "index.html", "service.py"):
        if source != APP:
            shutil.copy2(source / name, APP / name)
    (APP / "usb-power").chmod(0o755)
    binary = Path.home() / ".local/bin/usb-power"
    binary.parent.mkdir(parents=True, exist_ok=True)
    if binary.exists() and not binary.is_symlink():
        raise RuntimeError(f"Refusing to replace a regular file: {binary}")
    temporary = binary.with_name("usb-power.new")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(APP / "usb-power")
    temporary.replace(binary)
    jobs = [(LABEL, [sys.executable, str(APP / "web.py"), "--port", "8765"], {"KeepAlive": True})]
    for port in (1, 2):
        if (ROOT / f"port-{port}.start").is_file():
            jobs.append((f"com.kun.usb-power.port-{port}", ["/bin/bash", str(APP / "usb-power"), "cycle", "__tick", str(port)], {"StartInterval": 300}))
    for label, arguments, settings in jobs:
        config = {
            "Label": label, "ProgramArguments": arguments, "RunAtLoad": True,
            "EnvironmentVariables": {"HOME": str(Path.home()), "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"},
            "StandardOutPath": str(logs / f"{label}.out.log"),
            "StandardErrorPath": str(logs / f"{label}.err.log"),
            **settings,
        }
        path = AGENTS / f"{label}.plist"
        launch("bootout", f"{DOMAIN}/{label}", check=False)
        with path.open("wb") as stream:
            plistlib.dump(config, stream)
        result = launch("bootstrap", DOMAIN, str(path), check=False)
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
    print("Installed native background service: http://127.0.0.1:8765/")


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "install":
        install()
    elif action == "status":
        result = launch("print", f"{DOMAIN}/{LABEL}", check=False)
        if result.returncode:
            print("Web service is not loaded")
        else:
            for line in result.stdout.splitlines():
                if any(key in line for key in ("state =", "pid =", "last exit code =")):
                    print(line.strip())
        print(f"Logs: {ROOT / 'logs'}")
    elif action == "stop":
        launch("bootout", f"{DOMAIN}/{LABEL}", check=False)
        print("Web service stopped; charging cycles continue")
    elif action in ("start", "restart"):
        if not launch("print", f"{DOMAIN}/{LABEL}", check=False).returncode:
            launch("kickstart", "-k", f"{DOMAIN}/{LABEL}")
        else:
            launch("bootstrap", DOMAIN, str(AGENTS / f"{LABEL}.plist"))
        print("Web service started: http://127.0.0.1:8765/")
    else:
        raise RuntimeError("Usage: usb-power service {install|start|stop|restart|status}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
