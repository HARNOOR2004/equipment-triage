import { useEffect, useState } from "react";

export const PRIORITIES = ["low", "medium", "high", "critical"];

export function fmtDate(v) {
  if (!v) return "";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString();
}

export function Badge({ kind, children }) {
  return <span className={`badge b-${kind}`}>{children}</span>;
}

export function Banner({ kind = "error", title, children, onRetry }) {
  return (
    <div className={`banner banner-${kind}`} role={kind === "error" ? "alert" : "status"}>
      {title && <strong>{title}</strong>}
      {children && <div>{children}</div>}
      {onRetry && (
        <button type="button" className="btn small" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function Spinner({ label = "Loading…" }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setSlow(true), 5000);
    return () => clearTimeout(t);
  }, []);
  return (
    <div className="spinner-wrap">
      <div className="spinner" />
      <div>
        {label}
        {slow && (
          <div className="muted small">Still working…</div>
        )}
      </div>
    </div>
  );
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>;
}

export function useLoad(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    fn()
      .then((d) => alive && setState({ data: d, error: null, loading: false }))
      .catch((e) => alive && setState({ data: null, error: e, loading: false }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { ...state, reload: () => setTick((t) => t + 1) };
}

export function Citations({ refs, info }) {
  const [open, setOpen] = useState(null);
  if (!refs || refs.length === 0) return <div className="muted small">No citations</div>;
  const o = open ? info[open] : null;
  return (
    <div className="cites">
      <span className="muted small">Evidence:</span>
      {refs.map((r) => (
        <button
          key={r}
          type="button"
          className={`chip ${open === r ? "on" : ""}`}
          onClick={() => setOpen(open === r ? null : r)}
        >
          {r}
        </button>
      ))}
      {open && (
        <div className="cite-detail">
          <strong>{o ? o.title : open}</strong>
          {o && o.text && <p>{o.text}</p>}
        </div>
      )}
    </div>
  );
}