import { useEffect, useRef, useState } from "react";
import { api, getTechnician } from "../api.js";
import { Badge, Banner, Citations, Empty, PRIORITIES, Spinner, fmtDate, useLoad } from "../components/ui.jsx";

function buildInfo(report, analysis) {
  const info = {};
  ((analysis && analysis.retrieved_chunks) || []).forEach((c) => {
    info[c.id] = { title: `${c.id} — ${c.title}`, text: c.text };
  });
  (report.operating_events || []).forEach((e) => {
    info[e.id] = { title: `Operating event ${e.id}`, text: e.text };
  });
  ((analysis && analysis.threshold_results) || []).forEach((r) => {
    info[`SENSOR:${r.sensor}`] = { title: `Sensor check: ${r.sensor} (${r.status})`, text: r.message };
  });
  return info;
}

function ConfirmForm({ cause, rid, onDone }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(cause.description);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  if (!open) return <button type="button" className="btn small" onClick={() => setOpen(true)}>Record as confirmed finding…</button>;
  async function save() {
    setBusy(true); setErr(null);
    try {
      await api.addFinding(rid, { kind: "confirmed", text, evidence_refs: cause.evidence_refs });
      setOpen(false); onDone();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }
  return (
    <div className="stack small-gap">
      <div className="muted small">Only confirm after physical inspection. This is recorded as a technician finding.</div>
      <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} />
      {err && <span className="err">{err}</span>}
      <div className="row">
        <button type="button" className="btn small primary" disabled={busy || text.trim().length < 3} onClick={save}>Save confirmed finding</button>
        <button type="button" className="btn small" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </div>
  );
}

function WorkOrderPanel({ wo, onChange }) {
  const [title, setTitle] = useState(wo.title);
  const [description, setDescription] = useState(wo.description);
  const [priority, setPriority] = useState(wo.priority);
  const [stepsText, setStepsText] = useState((wo.steps || []).join("\n"));
  const [override, setOverride] = useState("");
  const [needOverride, setNeedOverride] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const readOnly = wo.status !== "draft";

  const payload = () => ({
    title, description, priority,
    steps: stepsText.split("\n").map((s) => s.trim()).filter(Boolean),
  });

  async function act(fn) {
    setBusy(true); setErr(null);
    try { await fn(); onChange(); }
    catch (e) {
      if (e.status === 422 && /override_reason/.test(e.message)) setNeedOverride(true);
      setErr(e.message);
    } finally { setBusy(false); }
  }
  const needName = () => {
    if (!getTechnician()) { setErr("Enter your name in the header (Technician) before approving or rejecting."); return true; }
    return false;
  };

  return (
    <div className="card stack">
      <div className="row between">
        <h3>Work order #{wo.id}</h3>
        <div><Badge kind={wo.status}>{wo.status}</Badge> <Badge kind={`p-${wo.priority}`}>{wo.priority}</Badge></div>
      </div>
      {!readOnly && <Banner kind="info">AI draft only. Nothing is approved until a technician approves it here.</Banner>}
      {readOnly && wo.reviewed_by && (
        <div className="muted small">Reviewed by {wo.reviewed_by} on {fmtDate(wo.reviewed_at)}{wo.rejection_reason ? ` — reason: ${wo.rejection_reason}` : ""}</div>
      )}
      <label>Title<input disabled={readOnly} value={title} onChange={(e) => setTitle(e.target.value)} /></label>
      <label>Description<textarea disabled={readOnly} rows={4} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
      <label>Priority
        <select disabled={readOnly} value={priority} onChange={(e) => setPriority(e.target.value)}>
          {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </label>
      <label>Steps (one per line)<textarea disabled={readOnly} rows={5} value={stepsText} onChange={(e) => setStepsText(e.target.value)} /></label>
      {err && <Banner title="Action failed">{err}</Banner>}
      {needOverride && (
        <label>Override reason (priority is below the rule-based minimum)
          <input value={override} onChange={(e) => setOverride(e.target.value)} placeholder="Why is a lower priority justified?" />
        </label>
      )}
      {!readOnly && !rejecting && (
        <div className="row wrap">
          <button className="btn" disabled={busy} onClick={() => act(() => api.editWO(wo.id, payload()))}>Save edits</button>
          <button className="btn primary" disabled={busy} onClick={() => { if (needName()) return; act(async () => { await api.editWO(wo.id, payload()); await api.approveWO(wo.id, override); }); }}>Approve</button>
          <button className="btn danger" disabled={busy} onClick={() => setRejecting(true)}>Reject…</button>
        </div>
      )}
      {!readOnly && rejecting && (
        <div className="stack small-gap">
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason for rejection (required)" />
          <div className="row">
            <button className="btn danger" disabled={busy || reason.trim().length < 3} onClick={() => { if (needName()) return; act(() => api.rejectWO(wo.id, reason)); }}>Confirm reject</button>
            <button className="btn" onClick={() => setRejecting(false)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ReportDetail({ id, autorun }) {
  const { data: report, error, loading, reload } = useLoad(() => api.getReport(id), [id]);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState(null);
  const [answers, setAnswers] = useState({});
  const [fText, setFText] = useState("");
  const [fKind, setFKind] = useState("observation");
  const [fErr, setFErr] = useState(null);
  const started = useRef(false);

  async function run() {
    setRunning(true); setRunError(null);
    const clean = {};
    Object.entries(answers).forEach(([q, a]) => { if (a.trim()) clean[q] = a.trim(); });
    try { await api.analyze(id, clean); reload(); }
    catch (e) { setRunError(e.message); }
    finally { setRunning(false); }
  }

  useEffect(() => {
    if (autorun && report && report.analyses.length === 0 && !started.current) {
      started.current = true;
      run();
    }
    // eslint-disable-next-line
  }, [autorun, report]);

  async function addFinding() {
    setFErr(null);
    try { await api.addFinding(id, { kind: fKind, text: fText, evidence_refs: [] }); setFText(""); reload(); }
    catch (e) { setFErr(e.message); }
  }

  if (loading && !report) return <Spinner label="Loading report…" />;
  if (error) return <Banner title="Could not load report" onRetry={reload}>{error.message}</Banner>;

  const analysis = report.analyses[0];
  const ai = analysis && analysis.ai_output;
  const info = buildInfo(report, analysis);
  const latestWO = report.work_orders[0];
  const olderWOs = report.work_orders.slice(1);
  const observations = report.findings.filter((f) => f.kind === "observation");
  const confirmed = report.findings.filter((f) => f.kind === "confirmed");

   return (
    <div className="stack">
      <div className="page-head">
        <div>
          <div className="crumbs"><a href="#/history">History</a> / Report #{report.id}</div>
          <h1>{report.equipment.identifier} <span className="h1-sub">{report.equipment.equipment_type.replace("_", " ")}</span></h1>
        </div>
        <a className="btn small" href={`#/equipment/${encodeURIComponent(report.equipment.identifier)}`}>Equipment history</a>
      </div>

      <div className="card facts">
        <div className="fact">
          <div className="fact-label">Report</div>
          <div>#{report.id}</div>
          <div className="muted small">{fmtDate(report.created_at)}</div>
        </div>
        <div className="fact wide">
          <div className="fact-label">Issue</div>
          <div>{report.issue_description}</div>
        </div>
        <div className="fact">
          <div className="fact-label">Operating events</div>
          {report.operating_events.length === 0 ? <div className="muted">none provided</div> : report.operating_events.map((e) => <div key={e.id} className="small">{e.id}: {e.text}</div>)}
        </div>
        <div className="fact">
          <div className="fact-label">Submitted readings</div>
          {report.sensors.length === 0 ? <div className="muted">none provided</div> : report.sensors.map((s) => <div key={s.id} className="small">{s.sensor_name} = {s.value ?? "—"}{s.unit ? " " + s.unit : ""}</div>)}
        </div>
      </div>

      {running && <Spinner label="Running analysis (retrieval + AI)…" />}
      {runError && <Banner title="Analysis request failed" onRetry={run}>{runError}</Banner>}

      {!analysis && !running && (
        <Empty>
          No analysis yet. <button className="btn primary" onClick={run}>Run analysis</button>
        </Empty>
      )}

      {analysis && analysis.status !== "success" && (
        <Banner kind="warn" title={`Analysis ${analysis.status}`}>
          {analysis.error} Deterministic threshold results are still shown below. <button className="btn small" onClick={run} disabled={running}>Retry analysis</button>
        </Banner>
      )}
      {analysis && ai && ai.validation_issues && ai.validation_issues.length > 0 && (
        <details className="card">
          <summary>Validation notes ({ai.validation_issues.length}) — AI output was corrected by the system</summary>
          <ul>{ai.validation_issues.map((v, i) => <li key={i}>{v}</li>)}</ul>
        </details>
      )}

      <div className="detail-grid">
        <div className="col-main">
          {analysis && (
            <section className="stack">
              <h2>Observations <span className="muted small">recorded facts and rule-based checks</span></h2>
              <div className="row"><span className="muted small">Overall severity</span> <Badge kind={analysis.severity}>{analysis.severity}</Badge></div>
              <div className="table-card">
                <table>
                  <thead><tr><th>Sensor</th><th>Status</th><th>Value</th><th>Rule</th><th>Note</th></tr></thead>
                  <tbody>
                    {analysis.threshold_results.map((r) => (
                      <tr key={r.sensor}>
                        <td>{r.sensor}</td>
                        <td><Badge kind={r.status}>{r.status}</Badge></td>
                        <td>{r.value ?? "—"} {r.unit || ""}</td>
                        <td className="small">{r.rule}</td>
                        <td className="small">{r.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {ai && ai.data_quality_notes.length > 0 && (
                <Banner kind="warn" title="Data quality">
                  <ul>{ai.data_quality_notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
                </Banner>
              )}
            </section>
          )}

          {analysis && ai && (
            <>
              <section className="stack">
                <h2>Possible causes <span className="muted small">hypotheses, not confirmed</span></h2>
                {ai.possible_causes.length === 0 && <Empty>The AI returned no cited causes.</Empty>}
                {ai.possible_causes.map((c, i) => (
                  <div className="card stack small-gap" key={i}>
                    <div className="row">
                      <Badge kind="hypothesis">Hypothesis</Badge>
                      <Badge kind={`lk-${c.likelihood}`}>{c.likelihood} likelihood</Badge>
                    </div>
                    <div>{c.description}</div>
                    <Citations refs={c.evidence_refs} info={info} />
                    <ConfirmForm cause={c} rid={report.id} onDone={reload} />
                  </div>
                ))}
              </section>

              <section className="stack">
                <h2>Follow-up questions</h2>
                {ai.follow_up_questions.length === 0 && <Empty>No follow-up questions.</Empty>}
                {ai.follow_up_questions.map((q, i) => (
                  <label key={i} className="card">
                    <strong>{q.question}</strong>
                    <div className="muted small">Why: {q.reason}</div>
                    <textarea rows={2} value={answers[q.question] || ""} onChange={(e) => setAnswers({ ...answers, [q.question]: e.target.value })} placeholder="Your answer" />
                  </label>
                ))}
                {ai.follow_up_questions.length > 0 && (
                  <div><button className="btn" disabled={running} onClick={run}>Re-analyze with my answers</button></div>
                )}
              </section>

              <section className="stack">
                <h2>Suggested inspection steps</h2>
                {ai.inspection_steps.length === 0 && <Empty>No cited inspection steps.</Empty>}
                <div className="card">
                  <ol className="steps">
                    {ai.inspection_steps.map((s, i) => (
                      <li key={i}>{s.instruction}<Citations refs={s.evidence_refs} info={info} /></li>
                    ))}
                  </ol>
                </div>
              </section>
            </>
          )}
        </div>

        <aside className="col-side">
          {analysis && ai && (
            <section className="stack">
              <h2>Maintenance priority</h2>
              <div className="card stack small-gap">
                <div className="row wrap">
                  <Badge kind={`p-${ai.suggested_priority}`}>{ai.suggested_priority}</Badge>
                  {ai.ai_original_priority !== ai.suggested_priority && (
                    <span className="small">AI suggested <strong>{ai.ai_original_priority}</strong>; raised by deterministic threshold rules.</span>
                  )}
                </div>
                <div>{ai.priority_reasoning}</div>
                <Citations refs={ai.priority_evidence_refs} info={info} />
              </div>
            </section>
          )}

          {latestWO && (
            <section className="stack">
              <h2>Draft work order</h2>
              <WorkOrderPanel key={`${latestWO.id}-${latestWO.status}`} wo={latestWO} onChange={reload} />
              {olderWOs.length > 0 && (
                <details className="card">
                  <summary>Earlier work orders ({olderWOs.length})</summary>
                  {olderWOs.map((w) => (
                    <div className="small" key={w.id}>#{w.id} <Badge kind={w.status}>{w.status}</Badge> <Badge kind={`p-${w.priority}`}>{w.priority}</Badge> {w.title}</div>
                  ))}
                </details>
              )}
            </section>
          )}

          <section className="stack">
            <h2>Findings</h2>
            <div className="card">
              <h3>Observations</h3>
              {observations.length === 0 ? <div className="muted small">None</div> : observations.map((f) => <div className="small" key={f.id}>• {f.text} <span className="muted">({f.source})</span></div>)}
            </div>
            <div className="card">
              <h3>Confirmed by technician</h3>
              {confirmed.length === 0 ? <div className="muted small">Nothing confirmed yet</div> : confirmed.map((f) => <div className="small" key={f.id}>• {f.text} <span className="muted">({f.source}, {fmtDate(f.created_at)})</span></div>)}
            </div>
            <div className="card stack small-gap">
              <div className="row">
                <select value={fKind} onChange={(e) => setFKind(e.target.value)}>
                  <option value="observation">Observation</option>
                  <option value="confirmed">Confirmed finding</option>
                </select>
                <input value={fText} onChange={(e) => setFText(e.target.value)} placeholder="Add a finding" />
                <button className="btn" disabled={fText.trim().length < 3} onClick={addFinding}>Add</button>
              </div>
              {fErr && <span className="err">{fErr}</span>}
            </div>
          </section>

          {analysis && analysis.retrieved_chunks.length > 0 && (
            <details className="card">
              <summary>Manual sections retrieved ({analysis.retrieved_chunks.length})</summary>
              {analysis.retrieved_chunks.map((c) => (
                <div key={c.id} className="small chunk"><strong>{c.id} — {c.title}</strong><div className="muted">{c.text}</div></div>
              ))}
            </details>
          )}
        </aside>
      </div>
    </div>
  );
}