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
