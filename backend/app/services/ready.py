from __future__ import annotations

import sqlite3


def room_active(conn: sqlite3.Connection, slot_code: str) -> bool:
    row = conn.execute(
        "SELECT active FROM slots WHERE code=?", (slot_code,)
    ).fetchone()
    return bool(row and row["active"] == 1)


def teacher_active(conn: sqlite3.Connection, executor_code: str) -> bool:
    row = conn.execute(
        "SELECT active FROM executors WHERE code=?", (executor_code,)
    ).fetchone()
    return bool(row and row["active"] == 1)


def overlap(
    a_start: int, a_end: int, b_start: int, b_end: int
) -> bool:
    return a_start < b_end and b_start < a_end


def resource_busy(
    conn: sqlite3.Connection,
    *,
    kind: str,
    resource_code: str,
    day: str,
    start_min: int,
    end_min: int,
    exclude_session: str | None = None,
) -> sqlite3.Row | None:
    # 分项释放口径：租约只在该资源尚未释放时继续占用它。
    # 半释放租约（status='partial'）中已释放的一项不再阻挡，未释放的一项仍然阻挡。
    col = "slot_code" if kind == "room" else "executor_code"
    release_col = "slot_released_at" if kind == "room" else "executor_released_at"
    rows = conn.execute(
        f"SELECT * FROM leases WHERE {col}=? AND day=? "
        f"AND status IN ('open','partial') AND {release_col} IS NULL",
        (resource_code, day),
    ).fetchall()
    for r in rows:
        if exclude_session and r["window_code"] == exclude_session:
            continue
        if overlap(start_min, end_min, r["start_min"], r["end_min"]):
            return r
    return None


def readiness(conn: sqlite3.Connection, session: sqlite3.Row) -> dict:
    reasons: list[str] = []
    if not room_active(conn, session["slot_code"]):
        reasons.append("算力槽未启用")
    if not teacher_active(conn, session["executor_code"]):
        reasons.append("执行器未启用")
    busy_room = resource_busy(
        conn,
        kind="room",
        resource_code=session["slot_code"],
        day=session["day"],
        start_min=session["start_min"],
        end_min=session["end_min"],
        exclude_session=session["code"],
    )
    if busy_room:
        reasons.append(f"算力槽已被租约 {busy_room['lease_no']} 占用")
    busy_teacher = resource_busy(
        conn,
        kind="teacher",
        resource_code=session["executor_code"],
        day=session["day"],
        start_min=session["start_min"],
        end_min=session["end_min"],
        exclude_session=session["code"],
    )
    if busy_teacher:
        reasons.append(f"执行器已被租约 {busy_teacher['lease_no']} 占用")
    return {"ready": len(reasons) == 0, "reasons": reasons}
