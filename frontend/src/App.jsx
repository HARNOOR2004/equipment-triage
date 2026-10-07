import { useEffect, useState } from "react";
import { getTechnician, setTechnician } from "./api.js";
import NewReport from "./pages/NewReport.jsx";
import ReportDetail from "./pages/ReportDetail.jsx";
import History from "./pages/History.jsx";
import Equipment from "./pages/Equipment.jsx";

function useHash() {
  const [hash, setHash] = useState(window.location.hash || "#/");
  useEffect(() => {
    const f = () => setHash(window.location.hash || "#/");
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return hash;
}

export default function App() {
  const hash = useHash();
  const [name, setName] = useState(getTechnician());
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);

  let page;
  if (parts[0] === "history") page = <History />;
  else if (parts[0] === "reports" && parts[1])
    page = <ReportDetail key={parts[1]} id={parts[1]} autorun={parts[2] === "run"} />;
  else if (parts[0] === "equipment" && parts[1])
    page = <Equipment identifier={decodeURIComponent(parts[1])} />;
  else page = <NewReport />;

  const section =
    parts[0] === "history" || parts[0] === "equipment" || parts[0] === "reports" ? "history" : "new";

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="logo">ET</div>
          <div>
            <div className="brand-name">Equipment Triage</div>
            <div className="brand-sub">Maintenance assistant</div>
          </div>
        </div>
        <nav className="nav">
          <a href="#/" className={section === "new" ? "active" : ""}>New report</a>
          <a href="#/history" className={section === "history" ? "active" : ""}>History</a>
        </nav>
        <div className="sidebar-foot">
          <label className="who">
            Technician
            <input
              value={name}
              placeholder="Your name"
              onChange={(e) => {
                setName(e.target.value);
                setTechnician(e.target.value);
              }}
            />
          </label>
          <div className="hint">Used for approvals and the audit log</div>
        </div>
      </aside>
      <main className="content">{page}</main>
    </div>
  );
}