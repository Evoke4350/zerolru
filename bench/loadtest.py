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
