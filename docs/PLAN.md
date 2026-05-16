# zerolru Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up `~/Projects/zerolru/` — a zero-dependency, stdlib-only Python LRU cache (with TTL) as a clean, SEO-discoverable GitHub repo, by porting the already-verified kata code.

**Architecture:** Single-module library `zerolru.py` (the product: `LRUCache`). Optional stdlib HTTP server `http_server.py` as a runnable showcase. All 23 verified tests ported into `test_zerolru.py`. SEO README, MIT LICENSE, bench harness with measured numbers. Local `git init` + initial commit. No third-party deps; not published to PyPI (README says vendor-the-file).

**Tech Stack:** Python 3.11+ stdlib only (`collections`, `http.server`, `unittest`, `random`). Git.

**Provenance:** Code is ported verbatim from the verified kata at
`/home/nathanib/Projects/mela-social/katas/lru-cache/solution.py` and
`/home/nathanih/Projects/mela-social/katas/lru-cache/test_solution.py`
(23 tests green, profiled). Behavior must remain identical (isomorphic port).

---

### Task 1: Repo skeleton + git

**Files:**
- Create: `/home/nathanib/Projects/zerolru/.gitignore`

- [ ] **Step 1: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
*.svg
```

- [ ] **Step 2: Init git**

Run: `git -C /home/nathanib/Projects/zerolru init -b main`
Expected: `Initialized empty Git repository`

---

### Task 2: Library module `zerolru.py`

**Files:**
- Create: `/home/nathanib/Projects/zerolru/zerolru.py`

- [ ] **Step 1: Write `zerolru.py`** — `LRUCache` ported verbatim from kata `solution.py:18-103`, server-only imports removed, module metadata added:

```python
"""zerolru — zero-dependency LRU cache with optional TTL for Python.

Pure standard library. No third-party dependencies. Python 3.11+.

    from zerolru import LRUCache
    c = LRUCache(capacity=128, ttl_seconds=60)
    c.put("k", "v")
    c.get("k")          # -> "v"  (or None if missing/expired)
    "k" in c            # membership (expiry-aware)
    len(c)              # live (non-expired) entry count

Not thread-safe by design: wrap calls in a lock if shared across threads.
See http_server.py for the lock-at-the-edge pattern.
"""
from __future__ import annotations

import time
from collections import OrderedDict, deque
from collections.abc import Callable, Hashable
from typing import Any

__all__ = ["LRUCache"]
__version__ = "0.1.0"


class LRUCache:
    """Bounded, least-recently-used cache with optional per-entry TTL.

    Parameters
    ----------
    capacity:
        Maximum number of entries. Must be a positive integer.
    ttl_seconds:
        If set, entries older than this (by seconds from the injected
        clock) are treated as absent. None disables TTL.
    now:
        Monotonic clock function returning seconds. Injectable so tests
        can advance time deterministically.
    """

    def __init__(
        self,
        capacity: int,
        ttl_seconds: float | None = None,
        *,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        if ttl_seconds is not None and ttl_seconds < 0:
            raise ValueError("ttl_seconds must be non-negative")
        self._capacity = capacity
        self._ttl = ttl_seconds
        self._now = now
        self._store: OrderedDict[Hashable, tuple[Any, float]] = OrderedDict()
        self._expiry: deque[tuple[float, Hashable]] = deque()

    def _expired(self, stamp: float) -> bool:
        return self._ttl is not None and self._now() - stamp > self._ttl

    def _purge(self, key: Hashable) -> bool:
        entry = self._store.get(key)
        if entry is None:
            return False
        if self._expired(entry[1]):
            del self._store[key]
            return False
        return True

    def get(self, key: Hashable) -> Any | None:
        """Return value for `key` or None if missing/expired.

        A successful get marks the entry as most-recently-used.
        """
        if not self._purge(key):
            return None
        value = self._store[key][0]
        self._store.move_to_end(key)
        return value

    def put(self, key: Hashable, value: Any) -> None:
        """Insert or update an entry. Updating refreshes recency and TTL."""
        stamp = self._now()
        self._store[key] = (value, stamp)
        self._store.move_to_end(key)
        if self._ttl is not None:
            self._expiry.append((stamp, key))
        while len(self._store) > self._capacity:
            self._store.popitem(last=False)

    def __len__(self) -> int:
        """Number of live (non-expired) entries."""
        if self._ttl is None:
            return len(self._store)
        store = self._store
        exp = self._expiry
        while exp:
            stamp, key = exp[0]
            entry = store.get(key)
            if entry is None or entry[1] != stamp:
                exp.popleft()
                continue
            if self._now() - stamp > self._ttl:
                del store[key]
                exp.popleft()
                continue
            break
        return len(store)

    def __contains__(self, key: object) -> bool:
        return self._purge(key)
```

- [ ] **Step 2: Smoke-check import**

Run: `cd /home/nathanib/Projects/zerolru && python -c "from zerolru import LRUCache,__version__;c=LRUCache(2);c.put('a',1);print(c.get('a'),__version__)"`
Expected: `1 0.1.0`

---

### Task 3: Optional HTTP server `http_server.py`

**Files:**
- Create: `/home/nathanib/Projects/zerolru/http_server.py`

- [ ] **Step 1: Write `http_server.py`** — server ported verbatim from kata `solution.py:106-186`, importing `LRUCache` from `zerolru`:

```python
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
```

---

### Task 4: Test suite `test_zerolru.py`

**Files:**
- Create: `/home/nathanib/Projects/zerolru/test_zerolru.py`

- [ ] **Step 1: Write `test_zerolru.py`** — kata `test_solution.py` content **verbatim**, with exactly two changes: (a) docstring line 1, (b) the import line `from solution import LRUCache, make_app` replaced by the two-line block below. Everything else (FakeClock, TestBasics, TestEviction, TestTTL, TestValidation, ServerHarness, TestServer, _RefCache, TestModelRefinement, `__main__`) is byte-identical to the verified kata file.

New header + imports (replaces kata lines 1-11):

```python
"""Tests for zerolru. Run: python -m unittest test_zerolru.py -v"""
from __future__ import annotations

import http.client
import json
import random
import threading
import unittest
from http.server import ThreadingHTTPServer

from http_server import make_app
from zerolru import LRUCache
```

All remaining lines: copy verbatim from
`/home/nathanib/Projects/mela-social/katas/lru-cache/test_solution.py:13-307`.

- [ ] **Step 2: Run full suite**

Run: `cd /home/nathanib/Projects/zerolru && python -m unittest test_zerolru.py`
Expected: `Ran 23 tests` ... `OK`

---

### Task 5: Example, bench, results

**Files:**
- Create: `/home/nathanib/Projects/zerolru/examples/basic_usage.py`
- Create: `/home/nathanib/Projects/zerolru/bench/loadtest.py`
- Create: `/home/nathanib/Projects/zerolru/bench/RESULTS.md`

- [ ] **Step 1: `examples/basic_usage.py`**

```python
"""Minimal zerolru usage: recency eviction + TTL expiry."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zerolru import LRUCache


def main() -> None:
    c = LRUCache(capacity=2)
    c.put("a", 1)
    c.put("b", 2)
    c.get("a")          # 'a' now most-recently-used
    c.put("c", 3)       # evicts least-recently-used -> 'b'
    print("a in c:", "a" in c, "| b in c:", "b" in c, "| len:", len(c))

    clock = {"t": 0.0}
    t = LRUCache(capacity=8, ttl_seconds=10, now=lambda: clock["t"])
    t.put("x", "fresh")
    clock["t"] = 11
    print("x after ttl:", t.get("x"), "| len:", len(t))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: `bench/loadtest.py`** — cleaned port of the verified harness:

```python
"""Closed-loop load generator for http_server.py.

Usage: python bench/loadtest.py <port> <total_requests> <workers>
Mix: 25% PUT, 75% GET, keep-alive connections (one per worker).
"""
import http.client
import sys
import threading
import time

HOST = "127.0.0.1"
PORT = int(sys.argv[1])
TOTAL = int(sys.argv[2])
WORKERS = int(sys.argv[3])
per = TOTAL // WORKERS
lat: list[float] = []
errs = [0]
lock = threading.Lock()


def worker() -> None:
    L: list[float] = []
    e = 0
    conn = http.client.HTTPConnection(HOST, PORT)
    for i in range(per):
        t = time.perf_counter()
        try:
            if i % 4 == 0:
                conn.request("PUT", f"/cache/k{i & 1023}", body="1")
            else:
                conn.request("GET", f"/cache/k{i & 1023}")
            r = conn.getresponse()
            r.read()
        except Exception:
            e += 1
            try:
                conn.close()
            except Exception:
                pass
            conn = http.client.HTTPConnection(HOST, PORT)
            continue
        L.append(time.perf_counter() - t)
    conn.close()
    with lock:
        lat.extend(L)
        errs[0] += e


def main() -> None:
    start = time.perf_counter()
    ts = [threading.Thread(target=worker) for _ in range(WORKERS)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    dur = time.perf_counter() - start
    n = len(lat)
    lat.sort()
    print(
        f"ok={n:,} err={errs[0]} dur={dur:.2f}s rps={n / dur:,.0f} "
        f"p50={lat[n // 2] * 1e3:.2f}ms "
        f"p95={lat[int(n * 0.95)] * 1e3:.2f}ms "
        f"p99={lat[int(n * 0.99)] * 1e3:.2f}ms"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: `bench/RESULTS.md`**

```markdown
# Benchmark results

Machine: AMD Ryzen 7 5700 (16 logical cores), 62 GB RAM, Python 3.14, localhost.
Methodology: profile-driven, one isomorphic change at a time, all 23 tests
green after every change (behavior proven unchanged).

## Cache hot path (`len()` under load, 40k-op mix)

| Case | Before | After | Speedup |
|------|--------|-------|---------|
| no-TTL `len()` | 0.917 s | 0.087 s | 10.5x (O(n) -> O(1) fast path) |
| TTL `len()`    | 1.299 s | 0.105 s | 12.4x (timestamp deque, prune prefix only) |

## HTTP server (`http_server.py`, 32 keep-alive clients)

| Metric | Baseline (HTTP/1.0, conn/req) | Tuned (keep-alive + TCP_NODELAY) |
|--------|-------------------------------|----------------------------------|
| Throughput | 4,746 rps (lossy) | 10,079 rps |
| Errors over 1,000,000 reqs | connection resets | 0 |
| p99 latency | ~40 ms (Nagle stall) | 6.48 ms |

Reproduce:
    PORT=8000 CAPACITY=2048 python http_server.py &
    python bench/loadtest.py 8000 1000000 32
```

---

### Task 6: SEO README, LICENSE, CHANGELOG

**Files:**
- Create: `/home/nathanib/Projects/zerolru/README.md`
- Create: `/home/nathanib/Projects/zerolru/LICENSE`
- Create: `/home/nathanib/Projects/zerolru/CHANGELOG.md`

- [ ] **Step 1: `README.md`** (SEO: H1 + description + sections target queries
  *python lru cache ttl*, *lru cache with expiry python*, *zero dependency
  cache python*, *thread-safe lru cache*; suggested GitHub topics listed):

```markdown
# zerolru — zero-dependency LRU cache with TTL for Python

A small, fast, **zero-dependency LRU (least-recently-used) cache with
optional per-entry TTL** for Python 3.11+. Pure standard library — nothing
to `pip install`. O(1) `get`/`put`, profiled and benchmarked.

> Keywords: python lru cache, lru cache ttl, lru cache with expiry,
> in-memory cache, zero dependency cache, stdlib cache.
> Suggested GitHub topics: `python` `lru-cache` `ttl` `cache` `zero-dependency` `stdlib`

## Features

- **Zero dependencies** — stdlib only. Vendor one file.
- **TTL / expiry** — optional per-entry time-to-live with an injectable clock.
- **True LRU** — recency-correct eviction on `get` and `put`.
- **O(1) hot paths** — `len()` is O(1) (no TTL) / amortized O(expired) (TTL).
- **Profiled** — 10.5x–12.4x `len()` speedups; see `bench/RESULTS.md`.
- **Tested** — 23 tests incl. a 48,000-op randomized model-refinement check.

## Install

Not on PyPI. Vendor the single file:

    curl -O https://raw.githubusercontent.com/<you>/zerolru/main/zerolru.py

(or copy `zerolru.py` into your project).

## Quickstart

```python
from zerolru import LRUCache

c = LRUCache(capacity=128, ttl_seconds=60)
c.put("user:42", {"name": "Ada"})
c.get("user:42")     # -> {'name': 'Ada'}  (or None if missing/expired)
"user:42" in c       # expiry-aware membership
len(c)               # live entry count
```

## API

| Member | Behavior |
|--------|----------|
| `LRUCache(capacity, ttl_seconds=None, *, now=time.monotonic)` | `capacity` ≥ 1; `ttl_seconds` ≥ 0 or None; `now` injectable clock. Raises `ValueError` on bad args. |
| `get(key)` | Value, or `None` if missing/expired. Marks most-recently-used. |
| `put(key, value)` | Insert/update. Refreshes recency **and** TTL. Evicts LRU past capacity. |
| `len(cache)` | Count of live (non-expired) entries. |
| `key in cache` | Expiry-aware membership. |

### TTL semantics

An entry expires when `now() - inserted_at > ttl_seconds`. Expired entries
are removed lazily on access (`get`, `in`, `len`). `now` must be monotonic
non-decreasing (the default `time.monotonic` is).

### Thread safety

`LRUCache` is **not** internally locked (kept allocation-free on the hot
path). Wrap calls in a `threading.Lock` if shared across threads —
`http_server.py` demonstrates the lock-at-the-edge pattern.

## Optional HTTP server

`http_server.py` exposes a cache over JSON (`PUT/GET /cache/{key}`,
`GET /len`). Tuned (HTTP/1.1 keep-alive + TCP_NODELAY): ~10k rps,
1,000,000 requests with 0 errors. See `bench/RESULTS.md`.

## License

MIT — see [LICENSE](LICENSE).
```

- [ ] **Step 2: `LICENSE`** (MIT, holder per user):

```
MIT License

Copyright (c) 2026 Nathaniel Bennett

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 3: `CHANGELOG.md`**

```markdown
# Changelog

## 0.1.0 — 2026-05-15

- Initial release: `LRUCache` with optional TTL, zero dependencies.
- O(1) `len()` fast path (no TTL); amortized prefix-prune `len()` (TTL).
- Optional tuned stdlib HTTP server (`http_server.py`).
- 23 tests incl. 48,000-op randomized model-refinement suite.
```

---

### Task 7: Verify + commit

- [ ] **Step 1: Full test gate**

Run: `cd /home/nathanib/Projects/zerolru && python -m unittest test_zerolru.py 2>&1 | tail -3`
Expected: `Ran 23 tests` ... `OK`

- [ ] **Step 2: Example smoke**

Run: `cd /home/nathanib/Projects/zerolru && python examples/basic_usage.py`
Expected: `a in c: True | b in c: False | len: 2` then `x after ttl: None | len: 0`

- [ ] **Step 3: Initial commit**

```bash
cd /home/nathanib/Projects/zerolru
git add -A
git commit -m "feat: zerolru 0.1.0 — zero-dependency LRU cache with TTL

Ported from a profiled, test-driven kata. 23 tests green incl. a
48k-op model-refinement suite. Optional tuned stdlib HTTP server.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

Expected: one commit created on `main`.

---

## Self-Review

- **Spec coverage:** name `zerolru` ✓ (module, README H1); GitHub-only no-packaging ✓ (no pyproject/CI; README "vendor the file", honest no-PyPI); new sibling dir + git init ✓ (Task 1, 7); MIT / Nathaniel Bennett ✓ (Task 6.2); runtime zero-dep stdlib ✓ (`zerolru.py` imports stdlib only); SEO ✓ (Task 6.1 keywords/topics/sections); consumable ✓ (single-file vendor + clear API table); perf story preserved ✓ (Task 5.3 real numbers + reproduce).
- **Placeholder scan:** none — all file bodies are literal; ported code given verbatim or by exact verified line range + exact two-line edit.
- **Type/name consistency:** `make_app`, `serve`, `_TunedServer`, `LRUCache`, `_RefCache`, `FakeClock` names identical across `zerolru.py` / `http_server.py` / `test_zerolru.py`; test imports match the two modules that define the symbols.
- **Scope:** single repo, one plan, self-contained. No decomposition needed.
