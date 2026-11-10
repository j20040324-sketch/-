import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

from market_lens.models import Market
from market_lens.storage import Store
from market_lens.web import Application, make_handler


class WebApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.database = os.path.join(self.tempdir.name, "test.sqlite3")
        store = Store(self.database)
        store.save([Market("m1", "polymarket", "Test event", "open", probability=0.6,
                           probability_basis="top_outcome_price", volume=12.0)],
                   "2026-01-01T00:00:00+00:00")
        store.save([Market("old", "polymarket", "Old event", "open", probability=0.2)],
                   "2025-12-31T00:00:00+00:00")
        store.close()
        self.app = Application(self.database)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:{}".format(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tempdir.cleanup()

    def get_json(self, path):
        with urlopen(self.base + path) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_health_and_market_list(self):
        self.assertEqual(self.get_json("/api/health")["status"], "ok")
        result = self.get_json("/api/markets?platform=polymarket")
        self.assertEqual(result["market_count"], 1)
        self.assertEqual(result["markets"][0]["market"]["market_id"], "m1")

    def test_market_detail_and_static_page(self):
        detail = self.get_json("/api/markets/polymarket/m1")
        self.assertEqual(detail["analysis"]["market"]["title"], "Test event")
        with urlopen(self.base + "/") as response:
            self.assertIn("text/html", response.headers.get("Content-Type"))
            self.assertIn("Market Lens", response.read().decode("utf-8"))

    def test_refresh_rejects_invalid_json(self):
        request = Request(self.base + "/api/refresh", data=b"invalid", headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(Exception) as error:
            urlopen(request)
        self.assertIn("400", str(error.exception))


if __name__ == "__main__":
    unittest.main()
