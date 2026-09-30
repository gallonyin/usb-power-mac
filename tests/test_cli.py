import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "usb-power"


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.bin = Path(self.temp.name) / "bin"
        self.home.mkdir()
        self.bin.mkdir()
        (self.home / "port-state").write_text("off")
        uhubctl = self.bin / "uhubctl"
        uhubctl.write_text("""#!/usr/bin/env bash
port=1
action=
while (($#)); do
  case "$1" in
    -p) port=$2; shift 2 ;;
    -a) action=$2; shift 2 ;;
    *) shift ;;
  esac
done
if [[ -n $action ]]; then
  printf '%s' "$action" > "$HOME/port-state"
else
  state=$(cat "$HOME/port-state")
  if [[ $state == on ]]; then
    echo "  Port $port: 0100 power"
  else
    echo "  Port $port: 0000 off"
  fi
fi
""")
        uhubctl.chmod(0o755)
        launchctl = self.bin / "launchctl"
        launchctl.write_text("#!/bin/sh\nexit 0\n")
        launchctl.chmod(0o755)
        self.env = {**os.environ, "HOME": str(self.home), "PATH": f"{self.bin}:{os.environ['PATH']}"}

    def run_cli(self, *args):
        return subprocess.run([str(SCRIPT), *args], env=self.env, text=True, capture_output=True, check=True).stdout

    def test_default_port_and_hub(self):
        self.assertIn("Port 1: off -> on", self.run_cli("on"))
        self.assertIn("Port 1: already on", self.run_cli("on"))
        self.assertIn("Hub: 2-1", self.run_cli("hub"))
        self.assertIn("Hub: 3-2", self.run_cli("hub", "3-2"))

    def test_cycle_transition_and_safe_stop(self):
        self.assertIn("cycle enabled", self.run_cli("cycle", "on", "2"))
        self.assertEqual((self.home / "port-state").read_text(), "on")
        start = self.home / "Library/Application Support/usb-power/port-2.start"
        start.write_text(str(int(time.time()) - 7 * 3600))
        self.assertIn("on -> off", self.run_cli("cycle", "__tick", "2"))
        self.assertEqual((self.home / "port-state").read_text(), "off")
        self.assertIn("cycle disabled", self.run_cli("cycle", "off", "2"))
        self.assertEqual((self.home / "port-state").read_text(), "on")
        self.assertFalse((self.home / "Library/LaunchAgents/com.kun.usb-power.port-2.plist").exists())


if __name__ == "__main__":
    unittest.main()
