import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import ai
from app.ai import AIOutput
from app.db import Base, get_db
from app.main import app

def fake_llm(prompt):
    return AIOutput.model_validate({
        "possible_causes": [{"description": "Bearing wear", "likelihood": "medium", "evidence_refs": ["PUMP-2.1"]}],
        "follow_up_questions": [{"question": "Any noise?", "reason": "cavitation"}],
        "inspection_steps": [{"instruction": "Check alignment", "evidence_refs": ["PUMP-3.1"]}],
        "suggested_priority": "low", "priority_reasoning": "x", "priority_evidence_refs": ["SENSOR:vibration"],
        "draft_work_order": {"title": "t", "description": "d", "priority": "low", "steps": ["s"]},
        "data_quality_notes": [],
    })

@pytest.fixture
def client(monkeypatch):
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, autoflush=False)
    def override():
        db = S()
        try: yield db
        finally: db.close()
    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(ai, "_call_llm", fake_llm)
    yield TestClient(app)
    app.dependency_overrides.clear()

def make_report(c):
    r = c.post("/reports", json={
        "equipment_type": "centrifugal_pump", "identifier": "P-101",
        "issue_description": "High vibration and crackling noise",
        "operating_events": ["Restarted after strainer cleaning"],
        "readings": [{"sensor_name": "vibration", "value": 7.5, "unit": "mm/s"}]})
    assert r.status_code == 201
    return r.json()["id"]

def test_validation_error(client):
    assert client.post("/reports", json={"equipment_type": "x", "identifier": "", "issue_description": "a"}).status_code == 422

def test_draft_never_auto_approved_and_floor_applied(client):
    rid = make_report(client)
    out = client.post(f"/reports/{rid}/analyze", json={}).json()
    wo = out["work_order"]
    assert wo["status"] == "draft"
    assert wo["priority"] == "critical"          # AI said low, rules raised it

def test_approve_needs_override_when_priority_lowered(client):
    rid = make_report(client)
    wid = client.post(f"/reports/{rid}/analyze", json={}).json()["work_order"]["id"]
    client.patch(f"/work-orders/{wid}", json={"priority": "low"})
    assert client.post(f"/work-orders/{wid}/approve", json={}).status_code == 422
    ok = client.post(f"/work-orders/{wid}/approve", json={"override_reason": "Sensor verified faulty"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    assert client.patch(f"/work-orders/{wid}", json={"title": "x"}).status_code == 409   # locked after approval

def test_reject_requires_reason_and_history_kept(client):
    rid = make_report(client)
    wid = client.post(f"/reports/{rid}/analyze", json={}).json()["work_order"]["id"]
    assert client.post(f"/work-orders/{wid}/reject", json={"reason": ""}).status_code == 422
    assert client.post(f"/work-orders/{wid}/reject", json={"reason": "Duplicate"}).json()["status"] == "rejected"
    h = client.get("/equipment/P-101/history").json()
    assert len(h["reports"]) == 1 and h["reports"][0]["work_orders"][0]["status"] == "rejected"