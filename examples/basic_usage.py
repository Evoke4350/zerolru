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
