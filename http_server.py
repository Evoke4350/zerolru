"""Optional stdlib HTTP server exposing a zerolru.LRUCache over JSON.

Showcase / proof — the library itself (zerolru.py) needs none of this.
Routes:  PUT /cache/{key}  ·  GET /cache/{key}  ·  GET /len  ·  GET /
Run:     PORT=8000 CAPACITY=128 TTL= python http_server.py
"""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote

from zerolru import LRUCache

_PREFIX = "/cache/"


def make_app(cache: LRUCache) -> type[BaseHTTPRequestHandler]:
    """Build a request handler bound to `cache`. Cache is injectable for tests."""
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        disable_nagle_algorithm = True

        def log_message(self, *args: Any) -> None:
            pass

        def _send(self, status: int, body: dict[str, Any] | None = None) -> None:
            raw = b"" if body is None else json.dumps(body).encode()
            self.send_response(status)
            if raw:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            if raw:
                self.wfile.write(raw)

        def do_GET(self) -> None:
            if self.path == "/":
                self._send(200, {"ok": True})
                return
            if self.path == "/len":
                with lock:
                    self._send(200, {"len": len(cache)})
                return
            if self.path.startswith(_PREFIX):
                key = unquote(self.path[len(_PREFIX):])
                with lock:
                    if key in cache:
                        self._send(200, {"value": cache.get(key)})
                    else:
                        self._send(404, {"error": "not found"})
                return
            self._send(404, {"error": "not found"})

        def do_PUT(self) -> None:
            if not self.path.startswith(_PREFIX):
                self._send(404, {"error": "not found"})
                return
            key = unquote(self.path[len(_PREFIX):])
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                value = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                self._send(400, {"error": "invalid json body"})
                return
            with lock:
                cache.put(key, value)
            self._send(204)

    return Handler


class _TunedServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 1024


def serve(host: str, port: int, cache: LRUCache) -> ThreadingHTTPServer:
    """Start a threaded HTTP server for `cache`. Returns the running server."""
    server = _TunedServer((host, port), make_app(cache))
    server.serve_forever()
    return server


if __name__ == "__main__":
    capacity = int(os.environ.get("CAPACITY", "128"))
    ttl_env = os.environ.get("TTL")
    ttl = float(ttl_env) if ttl_env else None
    port = int(os.environ.get("PORT", "8000"))
    print(f"zerolru server on :{port} (capacity={capacity}, ttl={ttl})")
    serve("0.0.0.0", port, LRUCache(capacity, ttl_seconds=ttl))
