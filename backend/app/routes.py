from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.db import get_db
from app import models as m
from app.schemas import *
from app.rules import THRESHOLDS, overall_severity
from app.ai import analyze_report, _priority_floor, PRIORITIES

router = APIRouter()

def actor(x_technician: str = Header(default="technician")) -> str:
    return (x_technician.strip() or "technician")[:100]

def row(o) -> dict:
    return {c.name: getattr(o, c.name) for c in o.__table__.columns}

def audit(db, etype, eid, action, who, details=None):
    db.add(m.AuditLog(entity_type=etype, entity_id=eid, action=action, actor=who, details=details or {}))

def get_or_404(db, model, id_):
    obj = db.get(model, id_)
    if not obj:
        raise HTTPException(404, f"{model.__name__} {id_} not found")
    return obj

def analysis_out(a: m.Analysis) -> dict:
    d = row(a)
    d["severity"] = overall_severity(a.threshold_results or [])
    return d

def report_full(db: Session, rep: m.Report) -> dict:
    q = lambda model: db.scalars(select(model).where(model.report_id == rep.id).order_by(model.id.desc())).all()
    return {
        **row(rep),
        "equipment": row(rep.equipment),
        "sensors": [row(s) for s in rep.sensors],
        "analyses": [analysis_out(a) for a in q(m.Analysis)],
        "work_orders": [row(w) for w in q(m.WorkOrder)],
        "findings": [row(f) for f in q(m.Finding)],
    }

# ---------- meta ----------
@router.get("/equipment-types")
def equipment_types():
    return {t: {s: c["unit"] for s, c in spec.items()} for t, spec in THRESHOLDS.items()}

# ---------- reports ----------
@router.post("/reports", status_code=201)
def create_report(body: ReportCreate, db: Session = Depends(get_db), who: str = Depends(actor)):
    eq = db.scalar(select(m.Equipment).where(m.Equipment.identifier == body.identifier))
    if eq and eq.equipment_type != body.equipment_type:
        raise HTTPException(409, f"{body.identifier} is already registered as {eq.equipment_type}")
    if not eq:
        eq = m.Equipment(equipment_type=body.equipment_type, identifier=body.identifier)
        db.add(eq); db.flush()
    events = [{"id": f"E{i}", "text": t.strip()} for i, t in enumerate(body.operating_events, 1) if t.strip()]
    rep = m.Report(equipment_id=eq.id, issue_description=body.issue_description.strip(), operating_events=events)
    rep.sensors = [m.SensorReading(sensor_name=r.sensor_name, value=r.value, unit=r.unit) for r in body.readings]
    db.add(rep); db.flush()
    db.add(m.Finding(report_id=rep.id, kind="observation", text=rep.issue_description,
                     evidence_refs=[], source="technician"))
    audit(db, "report", rep.id, "created", who)
    db.commit(); db.refresh(rep)
    return report_full(db, rep)

@router.get("/reports")
def list_reports(limit: int = 50, db: Session = Depends(get_db)):
    reps = db.scalars(select(m.Report).order_by(m.Report.id.desc()).limit(min(limit, 200))).all()
    out = []
    for r in reps:
        a = db.scalar(select(m.Analysis).where(m.Analysis.report_id == r.id).order_by(m.Analysis.id.desc()))
        w = db.scalar(select(m.WorkOrder).where(m.WorkOrder.report_id == r.id).order_by(m.WorkOrder.id.desc()))
        out.append({**row(r), "equipment": row(r.equipment),
                    "latest_analysis_status": a.status if a else None,
                    "latest_work_order": row(w) if w else None})
    return out

@router.get("/reports/{rid}")
def get_report(rid: int, db: Session = Depends(get_db)):
    return report_full(db, get_or_404(db, m.Report, rid))

@router.get("/equipment/{identifier}/history")
def equipment_history(identifier: str, db: Session = Depends(get_db)):
    eq = db.scalar(select(m.Equipment).where(m.Equipment.identifier == identifier))
    if not eq:
        raise HTTPException(404, "Equipment not found")
    reps = db.scalars(select(m.Report).where(m.Report.equipment_id == eq.id).order_by(m.Report.id.desc())).all()
    return {"equipment": row(eq), "reports": [report_full(db, r) for r in reps]}

# ---------- analysis ----------
@router.post("/reports/{rid}/analyze")
def analyze(rid: int, body: AnalyzeIn = AnalyzeIn(), db: Session = Depends(get_db), who: str = Depends(actor)):
    rep = get_or_404(db, m.Report, rid)
    readings = [{"sensor_name": s.sensor_name, "value": s.value, "unit": s.unit} for s in rep.sensors]
    res = analyze_report(rep.equipment.equipment_type, rep.equipment.identifier, rep.issue_description,
                         rep.operating_events, readings, body.answers)
    ai_out = {**res["ai_output"], "validation_issues": res["validation_issues"]} if res["ai_output"] else None
    an = m.Analysis(report_id=rid, status=res["status"], threshold_results=res["threshold_results"],
                    retrieved_chunks=res["retrieved_chunks"], ai_output=ai_out, error=res["error"])
    db.add(an); db.flush()
    wo = None
    if ai_out:
        db.execute(update(m.WorkOrder)
                   .where(m.WorkOrder.report_id == rid, m.WorkOrder.status == "draft")
                   .values(status="superseded"))
        d = ai_out["draft_work_order"]
        wo = m.WorkOrder(report_id=rid, analysis_id=an.id, title=d["title"][:200],
                         description=d["description"], priority=d["priority"], steps=d["steps"], status="draft")
        db.add(wo); db.flush()
        audit(db, "work_order", wo.id, "draft_created", "ai", {"analysis_id": an.id})
    audit(db, "analysis", an.id, "run", who, {"status": an.status, "answers": body.answers})
    db.commit(); db.refresh(an)
    return {"analysis": analysis_out(an), "work_order": row(wo) if wo else None}

# ---------- findings (observation vs confirmed, technician only) ----------
@router.post("/reports/{rid}/findings", status_code=201)
def add_finding(rid: int, body: FindingIn, db: Session = Depends(get_db), who: str = Depends(actor)):
    get_or_404(db, m.Report, rid)
    f = m.Finding(report_id=rid, kind=body.kind, text=body.text, evidence_refs=body.evidence_refs, source="technician")
    db.add(f); db.flush()
    audit(db, "finding", f.id, f"added_{body.kind}", who)
    db.commit(); db.refresh(f)
    return row(f)

# ---------- work orders ----------
def _draft_or_409(w: m.WorkOrder):
    if w.status != "draft":
        raise HTTPException(409, f"Work order is already {w.status}")

@router.patch("/work-orders/{wid}")
def edit_wo(wid: int, body: WorkOrderEdit, db: Session = Depends(get_db), who: str = Depends(actor)):
    w = get_or_404(db, m.WorkOrder, wid); _draft_or_409(w)
    changes = body.model_dump(exclude_none=True)
    for k, v in changes.items():
        setattr(w, k, v)
    audit(db, "work_order", w.id, "edited", who, {"fields": list(changes)})
    db.commit(); db.refresh(w)
    return row(w)

@router.post("/work-orders/{wid}/approve")
def approve_wo(wid: int, body: ApproveIn = ApproveIn(), db: Session = Depends(get_db), who: str = Depends(actor)):
    w = get_or_404(db, m.WorkOrder, wid); _draft_or_409(w)
    an = db.get(m.Analysis, w.analysis_id) if w.analysis_id else None
    floor = _priority_floor(an.threshold_results) if an else "low"
    reason = (body.override_reason or "").strip()
    if PRIORITIES.index(w.priority) < PRIORITIES.index(floor) and not reason:
        raise HTTPException(422, f"Priority is below rule-based minimum '{floor}'. Provide override_reason to approve.")
    w.status, w.reviewed_by, w.reviewed_at = "approved", who, datetime.now(timezone.utc)
    audit(db, "work_order", w.id, "approved", who, {"override_reason": reason or None, "rule_floor": floor})
    db.commit(); db.refresh(w)
    return row(w)

@router.post("/work-orders/{wid}/reject")
def reject_wo(wid: int, body: RejectIn, db: Session = Depends(get_db), who: str = Depends(actor)):
    w = get_or_404(db, m.WorkOrder, wid); _draft_or_409(w)
    w.status, w.rejection_reason = "rejected", body.reason
    w.reviewed_by, w.reviewed_at = who, datetime.now(timezone.utc)
    audit(db, "work_order", w.id, "rejected", who, {"reason": body.reason})
    db.commit(); db.refresh(w)
    return row(w)