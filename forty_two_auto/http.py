from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


class FetchError(RuntimeError):
    """Raised when an upstream HTTP JSON request fails."""


def get_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 12.0,
    retries: int = 3,
    user_agent: str = "forty-two-auto/0.1",
) -> Any:
    if params:
        query = urllib.parse.urlencode(params)
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{query}"

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": user_agent,
        },
    )
    last_exc: Optional[BaseException] = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code == 429 and attempt < retries:
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2.0 * (attempt + 1)
                time.sleep(delay)
                continue
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            break
    raise FetchError(f"Failed to fetch JSON from {url}: {last_exc}") from last_exc
