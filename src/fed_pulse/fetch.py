"""Tiny stdlib HTTP helper with retries (no third-party dependencies)."""

from __future__ import annotations

import time
import urllib.error
import urllib.request

from . import __version__

USER_AGENT = f"fed-pulse/{__version__} (+https://github.com/BrickerP/fed-pulse)"


class FetchError(RuntimeError):
    """Raised when a remote resource cannot be retrieved or parsed."""


def http_get(url: str, timeout: float = 45.0, retries: int = 2) -> str:
    """GET ``url`` and return the decoded body, retrying transient failures."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:  # 4xx are not worth retrying
            last_error = exc
            if 400 <= exc.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    raise FetchError(f"GET {url} failed: {last_error}")
