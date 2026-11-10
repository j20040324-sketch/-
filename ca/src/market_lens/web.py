"""Local web application with a small JSON API and static frontend."""

import argparse
import json
import mimetypes
import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from .models import Market
from .service import analyze_market, market_results, refresh
from .storage import Store


WEB_ROOT = os.path.join(os.path.dirname(__file__), "web")


class Application:
    def __init__(self, database: str):
        self.database = database
        self.lock = threading.Lock()
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.active_job: Optional[str] = None

    def open_store(self) -> Store:
        return Store(self.database)

    def start_refresh(self, limit: int) -> Tuple[Dict[str, Any], int]:
        with self.lock:
            if self.active_job:
                return self.jobs[self.active_job], 409
            job_id = uuid.uuid4().hex
            job = {"id": job_id, "status": "running", "started_at": None,
                   "finished_at": None, "provider_counts": {}, "provider_errors": [], "error": None}
            self.jobs[job_id] = job
            self.active_job = job_id

        def worker() -> None:
            from datetime import datetime, timezone
            job["started_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            store = self.open_store()
            try:
                result = refresh(store, limit)
                job.update(result)
                job["status"] = "completed" if not result["provider_errors"] else "completed_with_errors"
            except Exception as exc:
                job["status"] = "failed"
                job["error"] = str(exc)
            finally:
                store.close()
                job["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                with self.lock:
                    self.active_job = None

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return job, 202


def make_handler(app: Application):
    class Handler(BaseHTTPRequestHandler):
        server_version = "MarketLens/0.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            print("[web] {} - {}".format(self.address_string(), fmt % args))

        def send_json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            if path.startswith("/api/"):
                self.handle_api_get(path, parse_qs(parsed.query))
                return
            self.serve_static(path)

        def handle_api_get(self, path: str, query: Dict[str, Any]) -> None:
            if path == "/api/health":
                store = app.open_store()
                try:
                    self.send_json({"status": "ok", "latest_capture": store.latest_capture()})
                finally:
                    store.close()
                return
            if path == "/api/refresh/status":
                job_id = query.get("job", [""])[0]
                with app.lock:
                    job = app.jobs.get(job_id)
                if not job:
                    self.send_json({"error": "Refresh job not found"}, 404)
                else:
                    self.send_json(job)
                return
            if path == "/api/markets":
                store = app.open_store()
                try:
                    results = market_results(store)
                    platform = query.get("platform", ["all"])[0]
                    signal = query.get("signal", ["all"])[0]
                    search = query.get("q", [""])[0].strip().lower()
                    sort = query.get("sort", ["volume"])[0]
                    results = [row for row in results
                               if platform == "all" or row.market.platform == platform]
                    results = [row for row in results
                               if signal == "all" or (signal == "alerts" and row.anomaly_flags)
                               or (signal == "moving" and row.probability_change is not None)]
                    if search:
                        results = [row for row in results if search in row.market.title.lower()
                                   or search in row.market.market_id.lower()]
                    if sort == "probability_change":
                        results.sort(key=lambda row: abs(row.probability_change or 0), reverse=True)
                    elif sort == "end_time":
                        results.sort(key=lambda row: row.market.end_time or "9999")
                    else:
                        results.sort(key=lambda row: row.market.volume or 0, reverse=True)
                    latest = store.latest_capture()
                    self.send_json({"generated_at": latest, "market_count": len(results),
                                    "markets": [row.to_dict() for row in results]})
                finally:
                    store.close()
                return
            if path.startswith("/api/markets/"):
                parts = path[len("/api/markets/"):].split("/", 1)
                if len(parts) != 2:
                    self.send_json({"error": "Expected platform and market id"}, 400)
                    return
                store = app.open_store()
                try:
                    market = next((item for item in store.list_markets()
                                   if item.platform == parts[0] and item.market_id == parts[1]), None)
                    if not market:
                        self.send_json({"error": "Market not found"}, 404)
                        return
                    history = store.history(market, 100)
                    self.send_json({"analysis": analyze_market(store, market).to_dict(),
                                    "history": [item.__dict__ for item in history]})
                finally:
                    store.close()
                return
            self.send_json({"error": "Not found"}, 404)

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/api/refresh":
                self.send_json({"error": "Not found"}, 404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
                limit = max(1, min(int(payload.get("limit", 100)), 500))
            except (ValueError, TypeError, json.JSONDecodeError):
                self.send_json({"error": "Invalid refresh request"}, 400)
                return
            job, status = app.start_refresh(limit)
            self.send_json(job, status)

        def serve_static(self, path: str) -> None:
            relative = "index.html" if path in ("/", "") else path.lstrip("/")
            normalized = os.path.normpath(os.path.join(WEB_ROOT, relative))
            if not normalized.startswith(WEB_ROOT + os.sep) and normalized != os.path.join(WEB_ROOT, "index.html"):
                self.send_error(404)
                return
            if not os.path.isfile(normalized):
                self.send_error(404)
                return
            with open(normalized, "rb") as asset:
                body = asset.read()
            content_type = mimetypes.guess_type(normalized)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
                content_type += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Prediction Market Lens web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default=os.environ.get("MARKET_LENS_DB", "data/markets.sqlite3"))
    args = parser.parse_args()
    app = Application(args.db)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    print("Market Lens running at http://{}:{}/".format(args.host, args.port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
