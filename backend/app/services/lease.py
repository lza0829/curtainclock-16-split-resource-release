from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.services.ready import readiness, resource_busy


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bump(conn: sqlite3.Connection, key: str, delta: int) -> int:
    row = conn.execute("SELECT value FROM watermarks WHERE key=?", (key,)).fetchone()
    cur = int(row["value"]) if row else 0
    nxt = cur + delta
    conn.execute(
        "INSERT INTO watermarks(key, value, updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, nxt, _now()),
    )
    return nxt


def _conflict_mode(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT value FROM settings WHERE key='conflict_mode'"
    ).fetchone()
    return row["value"] if row else "reject"


RESOURCE_COLS = {
    "slot": ("slot_code", "slot_released_at"),
    "executor": ("executor_code", "executor_released_at"),
}


def _release_state(lease: sqlite3.Row) -> dict:
    return {
        "slot": lease["slot_released_at"] is not None,
        "executor": lease["executor_released_at"] is not None,
    }


def _finalize(conn: sqlite3.Connection, lease_no: str) -> dict:
    """两项资源都释放后收口：租约 closed、批窗 done、在途水位减一。

    调用方须保证此前该租约尚未 closed（水位只减一次）。
    """
    lease = conn.execute(
        "SELECT * FROM leases WHERE lease_no=?", (lease_no,)
    ).fetchone()
    conn.execute(
        "UPDATE leases SET status='closed', closed_at=? WHERE lease_no=?",
        (_now(), lease_no),
    )
    conn.execute(
        "UPDATE windows SET status='done' WHERE code=?",
        (lease["window_code"],),
    )
    open_n = _bump(conn, "open_leases", -1)
    return {"status": "closed", "window_done": True, "open_leases": open_n}


def open_lease(conn: sqlite3.Connection, window_code: str) -> dict:
    session = conn.execute(
        "SELECT * FROM windows WHERE code=?", (window_code,)
    ).fetchone()
    if session is None:
        raise ValueError(f"批窗不存在：{window_code}")
    if session["status"] == "live":
        raise ValueError("批窗已在占用中，勿重复开窗")
    if session["status"] == "done":
        raise ValueError("批窗已结束")

    ready = readiness(conn, session)
    if not ready["ready"]:
        mode = _conflict_mode(conn)
        for reason in ready["reasons"]:
            kind = "room" if "算力槽" in reason else ("teacher" if "执行器" in reason else "ready")
            resource = (
                session["slot_code"]
                if kind == "room"
                else (session["executor_code"] if kind == "teacher" else window_code)
            )
            conn.execute(
                "INSERT INTO conflicts(kind, window_code, resource_code, day, start_min, end_min, reason, created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    kind,
                    window_code,
                    resource,
                    session["day"],
                    session["start_min"],
                    session["end_min"],
                    reason,
                    _now(),
                ),
            )
            _bump(conn, "conflict_count", 1)
        # 底座贯彻 reject（冲突落库后由调用方提交）；候补算力槽留给后续题
        return {
            "ok": False,
            "error": "；".join(ready["reasons"]),
            "conflict_mode": mode,
        }

    if resource_busy(
        conn,
        kind="room",
        resource_code=session["slot_code"],
        day=session["day"],
        start_min=session["start_min"],
        end_min=session["end_min"],
    ) or resource_busy(
        conn,
        kind="teacher",
        resource_code=session["executor_code"],
        day=session["day"],
        start_min=session["start_min"],
        end_min=session["end_min"],
    ):
        raise ValueError("资源刚被占用，开窗失败")

    n = conn.execute("SELECT COUNT(*) c FROM leases").fetchone()["c"] + 1
    lease_no = f"L-{session['day'].replace('-', '')}-{n:04d}"
    conn.execute(
        "INSERT INTO leases(lease_no, window_code, slot_code, executor_code, day, start_min, end_min, status, opened_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (
            lease_no,
            window_code,
            session["slot_code"],
            session["executor_code"],
            session["day"],
            session["start_min"],
            session["end_min"],
            "open",
            _now(),
        ),
    )
    conn.execute(
        "UPDATE windows SET status='live' WHERE code=?", (window_code,)
    )
    open_n = _bump(conn, "open_leases", 1)
    return {
        "ok": True,
        "lease_no": lease_no,
        "window_code": window_code,
        "status": "open",
        "open_leases": open_n,
    }


def close_lease(conn: sqlite3.Connection, lease_no: str) -> dict:
    """关窗入口：一笔同时释放槽与执行器（捆绑同释，事务内原子）。

    任一项已在分释入口释放过则不再重复释放，但整笔仍在同一事务里收口；
    两项都释放后批窗结束、水位按租约减一。
    """
    lease = conn.execute(
        "SELECT * FROM leases WHERE lease_no=?", (lease_no,)
    ).fetchone()
    if lease is None:
        raise ValueError(f"租约不存在：{lease_no}")
    if lease["status"] == "closed":
        raise ValueError("租约已结束")
    now = _now()
    conn.execute(
        "UPDATE leases SET status='partial', "
        "slot_released_at=COALESCE(slot_released_at, ?), "
        "executor_released_at=COALESCE(executor_released_at, ?) "
        "WHERE lease_no=?",
        (now, now, lease_no),
    )
    done = _finalize(conn, lease_no)
    return {"lease_no": lease_no, **done}


def release_resource(
    conn: sqlite3.Connection, lease_no: str, resource: str
) -> dict:
    """分释入口：只释放一项资源，另一项继续占用。

    释放最后一项时才收口批窗并减水位；半释放期间状态记为 partial，
    未释的一项仍会阻挡对应资源的新开窗。
    """
    if resource not in RESOURCE_COLS:
        raise ValueError(f"未知资源项：{resource}")
    _, release_col = RESOURCE_COLS[resource]
    lease = conn.execute(
        "SELECT * FROM leases WHERE lease_no=?", (lease_no,)
    ).fetchone()
    if lease is None:
        raise ValueError(f"租约不存在：{lease_no}")
    if lease["status"] == "closed":
        raise ValueError("租约已结束")
    if lease[release_col] is not None:
        raise ValueError(f"{'算力槽' if resource == 'slot' else '执行器'}已释放，勿重复释放")

    conn.execute(
        f"UPDATE leases SET status='partial', {release_col}=? WHERE lease_no=?",
        (_now(), lease_no),
    )
    state = _release_state(
        conn.execute("SELECT * FROM leases WHERE lease_no=?", (lease_no,)).fetchone()
    )
    if state["slot"] and state["executor"]:
        done = _finalize(conn, lease_no)
        return {"lease_no": lease_no, "released": resource, **done}
    open_n = conn.execute(
        "SELECT value FROM watermarks WHERE key='open_leases'"
    ).fetchone()
    return {
        "lease_no": lease_no,
        "released": resource,
        "status": "partial",
        "slot_released": state["slot"],
        "executor_released": state["executor"],
        "window_done": False,
        "open_leases": int(open_n["value"]) if open_n else 0,
    }
