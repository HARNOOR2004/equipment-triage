import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Banner, Spinner, useLoad } from "../components/ui.jsx";

const SAMPLES = [
  {
    label: "Pump: high vibration",
    equipment_type: "centrifugal_pump",
    identifier: "P-101",
    issue: "High vibration and crackling noise since morning",
    events: ["Pump restarted after suction strainer cleaning"],
    readings: [["vibration", "7.5"], ["temperature", "82"], ["pressure", "8.2"]],
  },
  {
    label: "Compressor: conflicting temp",
    equipment_type: "air_compressor",
    identifier: "C-204",
    issue: "Discharge temperature alarm keeps flickering and the unit is running hot",
    events: ["High ambient temperature during afternoon shift", "Oil top-up done yesterday"],
    readings: [["temperature", "98"], ["temperature", "112"], ["pressure", "8.9"], ["vibration", "3.1"]],
  },
  {
    label: "Conveyor: missing sensors",
    equipment_type: "conveyor_motor",
    identifier: "M-12",
    issue: "Motor housing feels hot and there is a burning smell near the belt drive",
    events: ["Belt jammed for about 10 minutes earlier today"],
    readings: [["current", "31"]],
  },
];

export default function NewReport() {
  const types = useLoad(() => api.equipmentTypes(), []);
  const [type, setType] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [issue, setIssue] = useState("");
  const [events, setEvents] = useState([""]);
  const [readings, setReadings] = useState([]);
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState(null);
  const [busy, setBusy] = useState(false);

  const sensors = types.data && type ? Object.keys(types.data[type] || {}) : [];

  useEffect(() => {
    if (types.data && !type) pickType(Object.keys(types.data)[0]);
    // eslint-disable-next-line
  }, [types.data]);

  function pickType(t) {
    setType(t);
    setReadings(Object.keys(types.data[t]).map((s) => ({ sensor_name: s, value: "" })));
  }

  function applySample(s) {
    setType(s.equipment_type);
    setIdentifier(s.identifier);
    setIssue(s.issue);
    setEvents(s.events);
    setReadings(s.readings.map(([sensor_name, value]) => ({ sensor_name, value })));
    setErrors({});
  }

  async function submit(e) {
    e.preventDefault();
    const errs = {};
    if (!identifier.trim()) errs.identifier = "Equipment identifier is required";
    if (issue.trim().length < 10) errs.issue = "Describe the issue (at least 10 characters)";
    const clean = [];
    readings.forEach((r, i) => {
      if (r.value.trim() === "") return;
      const n = Number(r.value);
      if (Number.isNaN(n)) errs[`r${i}`] = "Must be a number";
      else clean.push({ sensor_name: r.sensor_name, value: n, unit: types.data[type][r.sensor_name] || null });
    });
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    setServerError(null);
    try {
      const rep = await api.createReport({
        equipment_type: type,
        identifier: identifier.trim(),
        issue_description: issue.trim(),
        operating_events: events.filter((x) => x.trim()),
        readings: clean,
      });
      window.location.hash = `#/reports/${rep.id}/run`;
    } catch (err) {
      setServerError(err.message);
      setBusy(false);
    }
  }

  if (types.loading && !types.data) return <Spinner label="Loading equipment types…" />;
  if (types.error) return <Banner title="Could not load equipment types" onRetry={types.reload}>{types.error.message}</Banner>;

   return (
    <form onSubmit={submit} className="stack">
      <div className="page-head">
        <div>
          <h1>New report</h1>
          <p className="sub">Describe the problem. Threshold rules, manual retrieval and AI triage run after you submit.</p>
        </div>
      </div>

      <div className="card samples">
        <span className="muted small">Quick samples:</span>
        {SAMPLES.map((s) => (
          <button type="button" key={s.label} className="btn small pill" onClick={() => applySample(s)}>
            {s.label}
          </button>
        ))}
      </div>

      {serverError && <Banner title="Could not submit report">{serverError}</Banner>}

      <div className="form-grid">
        <div className="stack">
          <div className="card stack">
            <h2>Equipment and issue</h2>
            <div className="grid2">
              <label>
                Equipment type
                <select value={type} onChange={(e) => pickType(e.target.value)}>
                  {Object.keys(types.data).map((t) => (
                    <option key={t} value={t}>{t.replace("_", " ")}</option>
                  ))}
                </select>
              </label>
              <label>
                Equipment identifier
                <input value={identifier} onChange={(e) => setIdentifier(e.target.value)} placeholder="e.g. P-101" />
                {errors.identifier && <span className="err">{errors.identifier}</span>}
              </label>
            </div>
            <label>
              Issue description
              <textarea rows={6} value={issue} onChange={(e) => setIssue(e.target.value)} placeholder="What is wrong? What did you see, hear or smell?" />
              {errors.issue && <span className="err">{errors.issue}</span>}
            </label>
          </div>

                <div className="card stack small-gap">
            <h2>Recent operating events</h2>
            {events.map((ev, i) => (
              <div className="row" key={i}>
                <input
                  value={ev}
                  placeholder="e.g. Restarted after maintenance"
                  onChange={(e) => setEvents(events.map((x, j) => (j === i ? e.target.value : x)))}
                />
                <button type="button" className="btn small" onClick={() => setEvents(events.filter((_, j) => j !== i))}>
                  Remove
                </button>
              </div>
            ))}
            <button type="button" className="btn small" onClick={() => setEvents([...events, ""])}>+ Add event</button>
          </div>
        </div>

        <div className="stack">
                   <div className="card stack small-gap">
            <h2>Sensor readings</h2>
            <div className="muted small">Optional. Leave blank if a reading is unavailable.</div>
            {readings.map((r, i) => (
              <div key={i}>
                <div className="row">
                  <select
                    value={r.sensor_name}
                    onChange={(e) => setReadings(readings.map((x, j) => (j === i ? { ...x, sensor_name: e.target.value } : x)))}
                  >
                    {sensors.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                  <input
                    value={r.value}
                    inputMode="decimal"
                    placeholder="value"
                    onChange={(e) => setReadings(readings.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))}
                  />
                  <span className="unit">{(types.data[type] || {})[r.sensor_name]}</span>
                  <button type="button" className="btn small" onClick={() => setReadings(readings.filter((_, j) => j !== i))}>
                    Remove
                  </button>
                </div>
                {errors[`r${i}`] && <span className="err">{errors[`r${i}`]}</span>}
              </div>
            ))}
            <button
              type="button"
              className="btn small"
              onClick={() => setReadings([...readings, { sensor_name: sensors[0], value: "" }])}
            >
              + Add another reading
            </button>
            <div className="muted small">Two different readings for the same sensor are flagged as conflicting.</div>
          </div>

          <div className="form-actions">
            <button className="btn primary lg" disabled={busy}>
              {busy ? "Submitting…" : "Submit and analyze"}
            </button>
          </div>
        </div>
      </div>
    </form>
  );
}