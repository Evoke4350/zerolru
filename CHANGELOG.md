# Changelog

## 0.1.0 — 2026-05-15

- Initial release: `LRUCache` with optional TTL, zero dependencies.
- O(1) `len()` fast path (no TTL); amortized prefix-prune `len()` (TTL).
- Optional tuned stdlib HTTP server (`http_server.py`).
- 23 tests incl. 48,000-op randomized model-refinement suite.
