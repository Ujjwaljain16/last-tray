"""HTTP abstraction and bounded retry. Used ONLY by the explicit retrieval command (src.pipeline.fetch).

Normal pipeline execution never imports this module's callers. The abstraction exists so retry, backoff and failure
handling can be tested with a fake client and no network at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from src.config import RetryPolicy

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_BACKOFF_SECONDS = 30.0
MAX_RETRY_AFTER_SECONDS = 60.0


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    content: bytes
    headers: Mapping[str, str]


class HttpError(Exception):
    """Base class for transport-level failures."""


class HttpTimeout(HttpError):
    pass


class HttpConnectionError(HttpError):
    pass


class HttpClient(Protocol):
    def get(self, url: str, *, params: Mapping[str, str] | None = None, timeout: float = 30.0) -> HttpResponse: ...


@dataclass(frozen=True)
class Attempt:
    number: int
    result: str            # ok | timeout | connection_error | HTTP <status>
    detail: str = ""


class FetchFailed(Exception):
    """A request could not be completed within the retry policy, or failed in a way retrying cannot fix."""

    def __init__(self, message: str, attempts: list[Attempt]):
        super().__init__(message)
        self.attempts = attempts


def _excerpt(content: bytes, limit: int = 240) -> str:
    return content[:limit].decode("utf-8", errors="replace").replace("\n", " ").strip()


def get_with_retry(client: HttpClient, url: str, params: Mapping[str, str] | None, policy: RetryPolicy,
                   sleep: Callable[[float], None]) -> tuple[HttpResponse, list[Attempt]]:
    """GET with bounded attempts and exponential backoff.

    Retried: timeouts, connection errors, HTTP 429/500/502/503/504. Not retried: any other non-200 status (for example FMI's
    HTTP 400 "Too long time interval requested"): retrying cannot fix a request that is wrong. Never loops forever.
    """
    attempts: list[Attempt] = []
    for n in range(1, policy.max_attempts + 1):
        retry_after: float | None = None
        try:
            resp = client.get(url, params=params, timeout=policy.timeout_seconds)
        except HttpTimeout as exc:
            attempts.append(Attempt(n, "timeout", str(exc)))
        except HttpConnectionError as exc:
            attempts.append(Attempt(n, "connection_error", str(exc)))
        else:
            if resp.status_code == 200:
                attempts.append(Attempt(n, "ok"))
                return resp, attempts
            attempts.append(Attempt(n, f"HTTP {resp.status_code}", _excerpt(resp.content)))
            if resp.status_code not in RETRYABLE_STATUS:
                raise FetchFailed(f"HTTP {resp.status_code} is not retryable: {_excerpt(resp.content)}", attempts)
            ra = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
            if ra and ra.strip().isdigit():
                retry_after = min(float(ra), MAX_RETRY_AFTER_SECONDS)
        if n < policy.max_attempts:
            backoff = min(policy.backoff_base_seconds * policy.backoff_factor ** (n - 1), MAX_BACKOFF_SECONDS)
            sleep(retry_after if retry_after is not None else backoff)
    last = attempts[-1]
    raise FetchFailed(f"gave up after {policy.max_attempts} attempts (last: {last.result} {last.detail})".strip(), attempts)
