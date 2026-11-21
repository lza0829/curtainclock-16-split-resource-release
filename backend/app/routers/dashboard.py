from __future__ import annotations

from fastapi import APIRouter

from app.db import connect

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard():
    conn = connect()
    try:
        day_row = conn.execute(
            "SELECT value FROM settings WHERE key='fixture_day'"
        ).fetchone()
        day = day_row["value"] if day_row else None
        open_leases = conn.execute(
            "SELECT value FROM watermarks WHERE key='open_leases'"
        ).fetchone()
        conflicts = conn.execute(
            "SELECT value FROM watermarks WHERE key='conflict_count'"
        ).fetchone()
        live_n = conn.execute(
            "SELECT COUNT(*) c FROM windows WHERE status='live'"
        ).fetchone()["c"]
        draft_n = conn.execute(
            "SELECT COUNT(*) c FROM windows WHERE status='draft'"
        ).fetchone()["c"]
        # 半释放可观测：处于分项释放中、仍有未释资源的租约
        partial_n = conn.execute(
            "SELECT COUNT(*) c FROM leases WHERE status='partial'"
        ).fetchone()["c"]
        holding_slot_n = conn.execute(
            "SELECT COUNT(*) c FROM leases WHERE status='partial' AND slot_released_at IS NULL"
        ).fetchone()["c"]
        holding_executor_n = conn.execute(
            "SELECT COUNT(*) c FROM leases WHERE status='partial' AND executor_released_at IS NULL"
        ).fetchone()["c"]
        return {
            "fixture_day": day,
            "open_leases": int(open_leases["value"]) if open_leases else 0,
            "conflict_count": int(conflicts["value"]) if conflicts else 0,
            "live_sessions": live_n,
            "draft_sessions": draft_n,
            "partial_leases": partial_n,
            "holding_slots": holding_slot_n,
            "holding_executors": holding_executor_n,
        }
    finally:
        conn.close()
