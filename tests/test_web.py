import importlib.util
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen


spec = importlib.util.spec_from_file_location("usb_power_web", Path(__file__).parents[1] / "web.py")
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_page_contains_controls(self):
        with urlopen(self.base) as response:
            page = response.read().decode()
        self.assertIn("周期充电", page)
        self.assertIn(web.TOKEN, page)

    def test_change_requires_token(self):
        request = Request(
            self.base + "/api/action",
            data=json.dumps({"port": "2", "mode": "power", "action": "off"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 403)
        error.exception.close()

    def test_valid_change_uses_cli_arguments(self):
        def fake_run(*args):
            if args == ("cycle", "on", "2"):
                return True, "Port 2: cycle enabled"
            if args[0] == "hub":
                return True, "Hub: 2-1"
            if args[0] == "status":
                return True, f"Port {args[1]}: on"
            return True, f"Port {args[2]}: cycle enabled"

        request = Request(
            self.base + "/api/action",
            data=json.dumps({"port": "2", "mode": "cycle", "action": "on"}).encode(),
            headers={"Content-Type": "application/json", "X-USB-Power-Token": web.TOKEN},
        )
        with patch.object(web, "run_cli", side_effect=fake_run) as run:
            with urlopen(request) as response:
                result = json.load(response)
        self.assertTrue(result["ok"])
        run.assert_any_call("cycle", "on", "2")


if __name__ == "__main__":
    unittest.main()
