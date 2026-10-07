import { api } from "../api.js";
import { Badge, Banner, Empty, Spinner, fmtDate, useLoad } from "../components/ui.jsx";

export default function Equipment({ identifier }) {
  const { data, error, loading, reload } = useLoad(() => api.history(identifier), [identifier]);
  if (loading && !data) return <Spinner label="Loading equipment history…" />;
  if (error) return <Banner title="Could not load equipment history" onRetry={reload}>{error.message}</Banner>;
  return (
    <div className="stack">
      <h1>{data.equipment.identifier} <span className="muted small">{data.equipment.equipment_type}</span></h1>
      {data.reports.length === 0 && <Empty>No reports for this equipment.</Empty>}
      {data.reports.map((r) => {
        const confirmed = r.findings.filter((f) => f.kind === "confirmed");
        return (
          <div className="card" key={r.id}>
            <div className="row between">
              <a href={`#/reports/${r.id}`}><strong>Report #{r.id}</strong></a>
              <span className="muted small">{fmtDate(r.created_at)}</span>
            </div>
            <p>{r.issue_description}</p>
            <div className="small"><strong>Confirmed findings:</strong> {confirmed.length === 0 ? <span className="muted">none recorded</span> : confirmed.map((f) => f.text).join("; ")}</div>
            <div className="small"><strong>Work orders:</strong></div>
            {r.work_orders.length === 0 && <div className="muted small">none</div>}
            {r.work_orders.map((w) => (
              <div className="small" key={w.id}>
                <Badge kind={w.status}>{w.status}</Badge> <Badge kind={`p-${w.priority}`}>{w.priority}</Badge> {w.title}
                {w.reviewed_by && <span className="muted"> — {w.reviewed_by}, {fmtDate(w.reviewed_at)}</span>}
                {w.rejection_reason && <span className="muted"> — reason: {w.rejection_reason}</span>}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}