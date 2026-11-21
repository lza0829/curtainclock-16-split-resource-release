import { useEffect, useState } from "react";
import { api } from "../api";

function fmtMin(m) {
  const h = String(Math.floor(m / 60)).padStart(2, "0");
  const mm = String(m % 60).padStart(2, "0");
  return `${h}:${mm}`;
}

const statusLabel = {
  open: "占用中",
  partial: "半释放",
  closed: "已释放",
};

function releaseTag(released, label) {
  return (
    <span className={`tag ${released ? "done" : "live"}`}>
      {label}·{released ? "已释" : "占用"}
    </span>
  );
}

export default function Leases() {
  const [rows, setRows] = useState([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  async function load() {
    setRows(await api.leases());
  }

  useEffect(() => {
    load().catch((e) => setErr(e.message));
  }, []);

  function report(r) {
    if (r.status === "closed") {
      setMsg(
        `租约 ${r.lease_no} 双资源已释，批窗结束；在途租约 ${r.open_leases}`
      );
    } else {
      const left = !r.slot_released ? "算力槽" : "执行器";
      setMsg(
        `租约 ${r.lease_no} 已释放${r.released === "slot" ? "算力槽" : "执行器"}；${left}仍占用，在途租约 ${r.open_leases}`
      );
    }
  }

  async function closeOne(lease_no) {
    setMsg("");
    setErr("");
    try {
      report(await api.closeLease(lease_no));
      await load();
    } catch (e) {
      setErr(e.message);
      await load();
    }
  }

  async function releaseOne(lease_no, resource) {
    setMsg("");
    setErr("");
    try {
      report(await api.releaseResource(lease_no, resource));
      await load();
    } catch (e) {
      setErr(e.message);
      await load();
    }
  }

  return (
    <section className="panel">
      <h2>租约</h2>
      {msg && <div className="msg">{msg}</div>}
      {err && <div className="msg err">{err}</div>}
      <table>
        <thead>
          <tr>
            <th>租约号</th>
            <th>批窗</th>
            <th>资源</th>
            <th>时段</th>
            <th>状态</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const closed = r.status === "closed";
            return (
              <tr key={r.lease_no}>
                <td>{r.lease_no}</td>
                <td>{r.window_code}</td>
                <td>
                  <div>{r.slot_code} / {r.executor_code}</div>
                  <div className="row-actions">
                    {releaseTag(r.slot_released, "槽")}
                    {releaseTag(r.executor_released, "执行器")}
                  </div>
                </td>
                <td>
                  {r.day} {fmtMin(r.start_min)}–{fmtMin(r.end_min)}
                </td>
                <td>
                  <span className={`tag ${r.status}`}>
                    {statusLabel[r.status] || r.status}
                  </span>
                  {r.holding?.length > 0 && (
                    <div>
                      <small>仍占：{r.holding.map((h) => (h === "slot" ? "算力槽" : "执行器")).join("、")}</small>
                    </div>
                  )}
                </td>
                <td>
                  <div className="row-actions">
                    <button
                      className="secondary"
                      disabled={closed}
                      onClick={() => closeOne(r.lease_no)}
                    >
                      关窗释放
                    </button>
                    <button
                      className="secondary"
                      disabled={closed || r.slot_released}
                      onClick={() => releaseOne(r.lease_no, "slot")}
                    >
                      释放算力槽
                    </button>
                    <button
                      className="secondary"
                      disabled={closed || r.executor_released}
                      onClick={() => releaseOne(r.lease_no, "executor")}
                    >
                      释放执行器
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
