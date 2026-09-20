"""Thin GoHighLevel client. Its job is to make failures legible and safe:
transient errors are retried with backoff, everything else raises immediately
with the status, GHL's message and trace id — and never the token."""
from __future__ import annotations

import json as _json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

BASE = "https://services.leadconnectorhq.com"
RETRY_STATUS = {429, 500, 502, 503, 504}
NETWORK_ERRORS = (urllib.error.URLError, TimeoutError, ConnectionError)


def http(method: str, url: str, *, headers: dict, params: dict | None = None,
         body: dict | None = None, timeout: int = 30) -> tuple[int, bytes]:
    """Standard library only, so the skill runs anywhere python3 does."""
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = _json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"User-Agent": "ghl-proposal-skill/1.0", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class GHLError(RuntimeError):
    def __init__(self, msg: str, *, status: int | None = None, trace_id: str | None = None,
                 retryable: bool = False):
        super().__init__(msg)
        self.status, self.trace_id, self.retryable = status, trace_id, retryable


class GHL:
    def __init__(self, token: str, location_id: str, on_event: Callable[[str], None] | None = None):
        self._token, self.location_id = token, location_id
        self.on_event = on_event or (lambda m: None)
        self.attempts = 0            # total HTTP attempts, for the run log
        self.inject: dict = {}       # fault injection, demo/testing only
        self._backoff = float(os.environ.get("GHL_BACKOFF_BASE", "1.0"))

    def _headers(self, path: str, method: str) -> dict:
        token = self._token
        # demo fault: a revoked/expired token on the estimate write. GHL's real
        # 401 comes back — only the credential is fake.
        if self.inject.get("hard") and method == "POST" and path == "/invoices/estimate":
            token = "pit-00000000-revoked-token-for-failure-demo"
        return {"Authorization": f"Bearer {token}", "Version": "2021-07-28",
                "Content-Type": "application/json"}

    def request(self, method: str, path: str, *, params: dict | None = None,
                json: dict | None = None, max_attempts: int = 4) -> dict:
        for attempt in range(1, max_attempts + 1):
            self.attempts += 1
            try:
                if (method == "POST" and path == "/invoices/estimate"
                        and self.inject.get("transient", 0) > 0):
                    self.inject["transient"] -= 1
                    raise GHLError("simulated 503 Service Unavailable (failure demo)",
                                   status=503, retryable=True)
                status, raw = http(method, BASE + path, headers=self._headers(path, method),
                                   params=params, body=json)
                if status < 300:
                    return _json.loads(raw) if raw else {}
                try:
                    body = _json.loads(raw)
                    detail = body.get("message") or body.get("error") or raw[:300].decode("utf-8", "replace")
                    trace = body.get("traceId")
                except ValueError:
                    detail, trace = raw[:300].decode("utf-8", "replace"), None
                if isinstance(detail, list):
                    detail = "; ".join(map(str, detail))
                raise GHLError(f"{method} {path} -> {status}: {detail}",
                               status=status, trace_id=trace,
                               # GHL's gateway sometimes answers a backend timeout with a 401
                               # ("Command timed out"); observed live. Not an auth problem.
                               retryable=status in RETRY_STATUS or "timed out" in str(detail).lower())
            except NETWORK_ERRORS as exc:
                err = GHLError(f"{method} {path} network error: {type(exc).__name__}",
                               retryable=True)
            except GHLError as exc:
                err = exc
            if not err.retryable or attempt == max_attempts:
                raise err
            wait = self._backoff * 2 ** (attempt - 1)
            self.on_event(f"transient failure ({err}); retry {attempt}/{max_attempts - 1} in {wait:g}s")
            time.sleep(wait)
        raise AssertionError("unreachable")

    # --- the handful of calls this skill needs -----------------------------
    def location(self) -> dict:
        return self.request("GET", f"/locations/{self.location_id}").get("location", {})

    def upsert_contact(self, *, name: str, email: str, company: str, phone: str) -> dict:
        body = {"locationId": self.location_id, "name": name, "email": email,
                "companyName": company}
        if phone:
            body["phone"] = phone
        return self.request("POST", "/contacts/upsert", json=body)

    def list_estimates(self, *, search: str = "", contact_id: str = "") -> list[dict]:
        params = {"altId": self.location_id, "altType": "location", "limit": 50, "offset": 0}
        if search:
            params["search"] = search
        if contact_id:
            params["contactId"] = contact_id
        return self.request("GET", "/invoices/estimate/list", params=params).get("estimates", [])

    def create_estimate(self, body: dict) -> dict:
        # single attempt on purpose: a 5xx can hide a write that succeeded, so the
        # caller re-checks for an existing estimate before every retry.
        return self.request("POST", "/invoices/estimate", json=body, max_attempts=1)

    def backoff(self, attempt: int) -> float:
        return self._backoff * 2 ** (attempt - 1)

    def user_id(self) -> str:
        if os.environ.get("GHL_USER_ID"):
            return os.environ["GHL_USER_ID"]
        users = self.request("GET", "/users/", params={"locationId": self.location_id}).get("users", [])
        if not users:
            raise GHLError("no users found in this location; set GHL_USER_ID")
        return users[0]["id"]

    def send_estimate(self, estimate_id: str, user_id: str, name: str) -> dict:
        return self.request("POST", f"/invoices/estimate/{estimate_id}/send", json={
            "altId": self.location_id, "altType": "location", "action": "email",
            "liveMode": True, "userId": user_id, "estimateName": name})

    def delete_estimate(self, estimate_id: str) -> dict:
        return self.request("DELETE", f"/invoices/estimate/{estimate_id}",
                            json={"altId": self.location_id, "altType": "location"})
