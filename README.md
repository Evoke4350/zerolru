# zerolru — zero-dependency LRU cache with TTL for Python

A small, fast, **zero-dependency LRU (least-recently-used) cache with
optional per-entry TTL** for Python 3.11+. Pure standard library — nothing
to `pip install`. O(1) `get`/`put`, profiled and benchmarked.

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
| `LRUCache(capacity, ttl_seconds=None, *, now=time.monotonic)` | `capacity` >= 1; `ttl_seconds` >= 0 or None; `now` injectable clock. Raises `ValueError` on bad args. |
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
