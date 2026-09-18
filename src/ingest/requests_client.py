"""The ONLY module in the ingestion layer that imports `requests`.

Kept separate so that everything used by a normal offline run is provably free of network code (a test checks this).
"""
from __future__ import annotations

from typing import Mapping

import requests

from src.ingest.http import HttpConnectionError, HttpError, HttpResponse, HttpTimeout

USER_AGENT = "last-tray/0.1 (explicit source retrieval; educational FDE assignment)"


class RequestsClient:
    def __init__(self, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def get(self, url: str, *, params: Mapping[str, str] | None = None, timeout: float = 30.0) -> HttpResponse:
        try:
            r = self._session.get(url, params=params, timeout=timeout, allow_redirects=True)
        except requests.Timeout as exc:
            raise HttpTimeout(str(exc)) from exc
        except requests.ConnectionError as exc:
            raise HttpConnectionError(str(exc)) from exc
        except requests.RequestException as exc:
            raise HttpError(str(exc)) from exc
        return HttpResponse(r.status_code, r.content, {k: v for k, v in r.headers.items()})
