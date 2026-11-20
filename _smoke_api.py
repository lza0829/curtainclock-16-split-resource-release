# -*- coding: utf-8 -*-
"""0-1 API smoke against running server on 11100."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:11100/api"


def call(method: str, path: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"detail": raw}
        return e.code, payload


def main() -> None:
    st, dash = call("GET", "/dashboard")
    assert st == 200, dash
    print("dashboard", dash)

    st, open1 = call("POST", "/leases/open", {"window_code": "W-DIM-01"})
    assert st == 200, open1
    print("open1", open1)

    st, created = call(
        "POST",
        "/windows",
        {
            "code": "W-DIM-DUP",
            "title": "冲突试窗",
            "subject": "ETL",
            "slot_code": "S-ETL-01",
            "executor_code": "E-BI-01",
            "day": "2026-11-20",
            "start_min": 540,
            "end_min": 630,
        },
    )
    assert st == 200, created
    st, conflict = call("POST", "/leases/open", {"window_code": "W-DIM-DUP"})
    assert st == 409, conflict
    print("conflict", conflict)

    st, closed = call("POST", "/leases/close", {"lease_no": open1["lease_no"]})
    assert st == 200, closed
    print("closed", closed)
    print("SMOKE OK")


if __name__ == "__main__":
    main()
