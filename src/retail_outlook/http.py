"""Bounded, identified HTTP retrieval with immutable response caching."""
from __future__ import annotations

import logging
import time
from urllib.parse import urlsplit

import httpx

from retail_outlook.storage import Store

LOG = logging.getLogger(__name__)


class Fetcher:
    def __init__(self, store: Store, timeout: float = 45):
        self.store = store
        self.client = httpx.Client(timeout=timeout, follow_redirects=True,
                                   headers={"User-Agent": "RetailOutlookResearch/0.1 (personal research)"})
        self.cache: dict[str, tuple[bytes, dict]] = {}
        self.last_by_host: dict[str, float] = {}

    def get(self, source: str, url: str) -> tuple[bytes, dict]:
        if url in self.cache:
            return self.cache[url]
        host = urlsplit(url).netloc
        time.sleep(max(0, 1.0 - (time.monotonic() - self.last_by_host.get(host, 0))))
        for attempt in range(3):
            self.last_by_host[host] = time.monotonic()
            try:
                response = self.client.get(url)
                if response.status_code in (401, 403):
                    response.raise_for_status()  # No bypass or repeated authentication retries.
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        delay = min(float(response.headers.get("Retry-After", 2 ** (attempt + 1))), 15)
                        time.sleep(delay)
                        continue
                response.raise_for_status()
                if len(response.content) > 30_000_000:
                    raise ValueError("Response exceeds collector size budget")
                record = self.store.save_raw(source, str(response.url), response.content,
                    {"status_code": response.status_code, "content_type": response.headers.get("content-type"),
                     "etag": response.headers.get("etag"), "last_modified": response.headers.get("last-modified")})
                self.cache[url] = (response.content, record)
                return self.cache[url]
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 2:
                    raise
                time.sleep(2 ** (attempt + 1))
        raise RuntimeError(f"Fetch exhausted: {source}")

    def close(self) -> None:
        self.client.close()
