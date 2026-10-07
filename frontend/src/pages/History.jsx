import { useState } from "react";
import { api } from "../api.js";
import { Badge, Banner, Empty, Spinner, fmtDate, useLoad } from "../components/ui.jsx";

export default function History() {
  const { data, error, loading, reload } = useLoad(() => api.listReports(), []);
  const [q, setQ] = useState("");
  if (loading && !data) return <Spinner label="Loading reports…" />;
  if (error) return <Banner title="Could not load history" onRetry={reload}>{error.message}</Banner>;
  const rows = data.filter((r) => r.equipment.identifier.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Report history</h1>
          <p className="sub">{data.length} report{data.length === 1 ? "" : "s"} recorded</p>
        </div>
        <input className="search" placeholder="Filter by equipment identifier" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {data.length === 0 ? (
        <Empty>No reports yet. <a href="#/">Create the first report.</a></Empty>
      ) : rows.length === 0 ? (
        <Empty>No reports match that identifier.</Empty>
      ) : (
        <div className="table-card">
          <table>
            <thead>
              <tr><th>#</th><th>Equipment</th><th>Issue</th><th>Created</th><th>Analysis</th><th>Work order</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td><a href={`#/reports/${r.id}`}>{r.id}</a></td>
                  <td>
                    <a href={`#/equipment/${encodeURIComponent(r.equipment.identifier)}`}>{r.equipment.identifier}</a>
                    <div className="muted small">{r.equipment.equipment_type}</div>
                  </td>
                  <td>{r.issue_description.slice(0, 90)}</td>
                  <td className="small">{fmtDate(r.created_at)}</td>
                  <td>{r.latest_analysis_status ? <Badge kind={r.latest_analysis_status}>{r.latest_analysis_status}</Badge> : <span className="muted">not run</span>}</td>
                  <td>
                    {r.latest_work_order ? (
                      <>
                        <Badge kind={r.latest_work_order.status}>{r.latest_work_order.status}</Badge>{" "}
                        <Badge kind={`p-${r.latest_work_order.priority}`}>{r.latest_work_order.priority}</Badge>
                      </>
                    ) : <span className="muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}