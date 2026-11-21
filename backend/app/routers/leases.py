from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import connect, transaction
from app.services import lease as lease_svc

router = APIRouter(tags=["leases"])


class OpenBody(BaseModel):
    window_code: str


class CloseBody(BaseModel):
    lease_no: str


class ReleaseBody(BaseModel):
    lease_no: str
    resource: str


@router.get("/leases")
def list_leases():
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM leases ORDER BY id DESC"
        ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["slot_released"] = r["slot_released_at"] is not None
            item["executor_released"] = r["executor_released_at"] is not None
            item["holding"] = [
                name
                for name, rel in (
                    ("slot", item["slot_released"]),
                    ("executor", item["executor_released"]),
                )
                if not rel and r["status"] != "closed"
            ]
            out.append(item)
        return out
    finally:
        conn.close()


@router.get("/conflicts")
def list_conflicts():
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM conflicts ORDER BY id DESC LIMIT 100"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/leases/open")
def open_lease(body: OpenBody):
    try:
        with transaction() as conn:
            result = lease_svc.open_lease(conn, body.window_code)
        if result.get("ok") is False:
            raise HTTPException(409, result.get("error") or "开窗冲突")
        return result
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/leases/close")
def close_lease(body: CloseBody):
    try:
        with transaction() as conn:
            return lease_svc.close_lease(conn, body.lease_no)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/leases/release")
def release_resource(body: ReleaseBody):
    try:
        with transaction() as conn:
            return lease_svc.release_resource(conn, body.lease_no, body.resource)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
