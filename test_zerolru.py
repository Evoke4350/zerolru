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


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class TestBasics(unittest.TestCase):
    def test_put_then_get(self) -> None:
        c = LRUCache(2)
        c.put("a", 1)
        self.assertEqual(c.get("a"), 1)

    def test_get_missing_returns_none(self) -> None:
        c = LRUCache(2)
        self.assertIsNone(c.get("missing"))

    def test_update_existing_key(self) -> None:
        c = LRUCache(2)
        c.put("a", 1)
        c.put("a", 2)
        self.assertEqual(c.get("a"), 2)
        self.assertEqual(len(c), 1)

    def test_len_reflects_entries(self) -> None:
        c = LRUCache(3)
        self.assertEqual(len(c), 0)
        c.put("a", 1)
        c.put("b", 2)
        self.assertEqual(len(c), 2)

    def test_contains(self) -> None:
        c = LRUCache(2)
        c.put("a", 1)
        self.assertIn("a", c)
        self.assertNotIn("b", c)


class TestEviction(unittest.TestCase):
    def test_evicts_least_recently_used(self) -> None:
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.put("c", 3)
        self.assertNotIn("a", c)
        self.assertIn("b", c)
        self.assertIn("c", c)

    def test_get_refreshes_recency(self) -> None:
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.get("a")
        c.put("c", 3)
        self.assertIn("a", c)
        self.assertNotIn("b", c)

    def test_update_refreshes_recency(self) -> None:
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.put("a", 11)
        c.put("c", 3)
        self.assertIn("a", c)
        self.assertNotIn("b", c)

    def test_capacity_one(self) -> None:
        c = LRUCache(1)
        c.put("a", 1)
        c.put("b", 2)
        self.assertNotIn("a", c)
        self.assertEqual(c.get("b"), 2)


class TestTTL(unittest.TestCase):
    def test_expired_entry_returns_none(self) -> None:
        clk = FakeClock()
        c = LRUCache(2, ttl_seconds=10, now=clk)
        c.put("a", 1)
        clk.advance(11)
        self.assertIsNone(c.get("a"))

    def test_expired_entry_not_in_len(self) -> None:
        clk = FakeClock()
        c = LRUCache(2, ttl_seconds=10, now=clk)
        c.put("a", 1)
        clk.advance(11)
        self.assertEqual(len(c), 0)

    def test_expired_entry_not_in_contains(self) -> None:
        clk = FakeClock()
        c = LRUCache(2, ttl_seconds=10, now=clk)
        c.put("a", 1)
        clk.advance(11)
        self.assertNotIn("a", c)

    def test_put_refreshes_ttl(self) -> None:
        clk = FakeClock()
        c = LRUCache(2, ttl_seconds=10, now=clk)
        c.put("a", 1)
        clk.advance(8)
        c.put("a", 2)
        clk.advance(5)
        self.assertEqual(c.get("a"), 2)

    def test_no_ttl_means_no_expiry(self) -> None:
        clk = FakeClock()
        c = LRUCache(2, now=clk)
        c.put("a", 1)
        clk.advance(10_000)
        self.assertEqual(c.get("a"), 1)


class TestValidation(unittest.TestCase):
    def test_zero_capacity_raises(self) -> None:
        with self.assertRaises(ValueError):
            LRUCache(0)

    def test_negative_capacity_raises(self) -> None:
        with self.assertRaises(ValueError):
            LRUCache(-1)

    def test_negative_ttl_raises(self) -> None:
        with self.assertRaises(ValueError):
            LRUCache(2, ttl_seconds=-1)


class ServerHarness:
    def __init__(self, cache: LRUCache) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_app(cache))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def request(
        self, method: str, path: str, body: str | None = None
    ) -> tuple[int, str]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(method, path, body=body)
        resp = conn.getresponse()
        payload = resp.read().decode()
        conn.close()
        return resp.status, payload

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class TestServer(unittest.TestCase):
    def _harness(self, cache: LRUCache) -> ServerHarness:
        h = ServerHarness(cache)
        self.addCleanup(h.close)
        return h

    def test_put_then_get_http(self) -> None:
        h = self._harness(LRUCache(2))
        status, _ = h.request("PUT", "/cache/a", "1")
        self.assertEqual(status, 204)
        status, payload = h.request("GET", "/cache/a")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload), {"value": 1})

    def test_get_missing_returns_404(self) -> None:
        h = self._harness(LRUCache(2))
        status, _ = h.request("GET", "/cache/nope")
        self.assertEqual(status, 404)

    def test_len_endpoint(self) -> None:
        h = self._harness(LRUCache(3))
        h.request("PUT", "/cache/a", "1")
        h.request("PUT", "/cache/b", "2")
        status, payload = h.request("GET", "/len")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload), {"len": 2})

    def test_health(self) -> None:
        h = self._harness(LRUCache(2))
        status, payload = h.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload), {"ok": True})

    def test_ttl_expired_returns_404(self) -> None:
        clk = FakeClock()
        h = self._harness(LRUCache(2, ttl_seconds=10, now=clk))
        h.request("PUT", "/cache/a", "1")
        clk.advance(11)
        status, _ = h.request("GET", "/cache/a")
        self.assertEqual(status, 404)


class _RefCache:
    def __init__(self, capacity, ttl_seconds, now):
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 1:
            raise ValueError
        if ttl_seconds is not None and ttl_seconds < 0:
            raise ValueError
        self.cap = capacity
        self.ttl = ttl_seconds
        self.now = now
        self.data = {}
        self.order = []

    def _expired(self, stamp):
        return self.ttl is not None and self.now() - stamp > self.ttl

    def _drop(self, key):
        del self.data[key]
        self.order.remove(key)

    def _live(self, key):
        if key not in self.data:
            return False
        if self._expired(self.data[key][1]):
            self._drop(key)
            return False
        return True

    def get(self, key):
        if not self._live(key):
            return None
        self.order.remove(key)
        self.order.append(key)
        return self.data[key][0]

    def put(self, key, value):
        self.data[key] = (value, self.now())
        if key in self.order:
            self.order.remove(key)
        self.order.append(key)
        while len(self.data) > self.cap:
            victim = self.order.pop(0)
            del self.data[victim]

    def __len__(self):
        if self.ttl is None:
            return len(self.data)
        for key in list(self.data):
            if self._expired(self.data[key][1]):
                self._drop(key)
        return len(self.data)

    def __contains__(self, key):
        return self._live(key)


class TestModelRefinement(unittest.TestCase):
    SEEDS = [1, 2, 3, 7, 13, 42, 99, 1234, 2026, 65535]
    KEYS = [f"k{i}" for i in range(6)]

    def _run(self, seed, capacity, ttl):
        rng = random.Random(seed)
        clk = FakeClock()
        impl = LRUCache(capacity, ttl_seconds=ttl, now=clk)
        ref = _RefCache(capacity, ttl_seconds=ttl, now=clk)
        for step in range(400):
            ctx = (seed, capacity, ttl, step)
            choice = rng.randrange(5 if ttl is not None else 4)
            if choice == 0:
                k = rng.choice(self.KEYS)
                v = rng.randint(1, 10_000)
                impl.put(k, v)
                ref.put(k, v)
            elif choice == 1:
                k = rng.choice(self.KEYS)
                self.assertEqual(impl.get(k), ref.get(k), ctx)
            elif choice == 2:
                k = rng.choice(self.KEYS)
                self.assertEqual(k in impl, k in ref, ctx)
            elif choice == 3:
                self.assertEqual(len(impl), len(ref), ctx)
            else:
                clk.advance(rng.choice([1, 3, 4, 5, 6, 11]))
            self.assertLessEqual(len(impl), capacity, ctx)
            self.assertEqual(len(impl), len(ref), ctx)
            for k in self.KEYS:
                self.assertEqual(k in impl, k in ref, ctx)

    def test_refines_reference_spec(self):
        for seed in self.SEEDS:
            for capacity in (1, 2, 3, 5):
                for ttl in (None, 5, 10):
                    with self.subTest(seed=seed, capacity=capacity, ttl=ttl):
                        self._run(seed, capacity, ttl)


if __name__ == "__main__":
    unittest.main()
