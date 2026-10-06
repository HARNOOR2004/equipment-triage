from app import ai
from app.ai import AIOutput, AIError

def fake_output(prio="low", refs=None, cause_refs=None):
    return AIOutput.model_validate({
        "possible_causes": [
            {"description": "Bearing wear", "likelihood": "medium", "evidence_refs": cause_refs or ["PUMP-2.1"]},
            {"description": "Made-up cause", "likelihood": "low", "evidence_refs": ["FAKE-9.9"]},
        ],
        "follow_up_questions": [{"question": "Any unusual noise?", "reason": "Cavitation check"}],
        "inspection_steps": [{"instruction": "Check alignment", "evidence_refs": ["PUMP-3.1"]}],
        "suggested_priority": prio,
        "priority_reasoning": "test",
        "priority_evidence_refs": refs or ["SENSOR:vibration"],
        "draft_work_order": {"title": "t", "description": "d", "priority": prio, "steps": ["s"]},
        "data_quality_notes": [],
    })

READINGS = [{"sensor_name": "vibration", "value": 7.5, "unit": "mm/s"}]
EVENTS = [{"id": "E1", "text": "Loud noise during startup"}]

def run():
    return ai.analyze_report("centrifugal_pump", "P-101", "high vibration and noise", EVENTS, READINGS)

def test_priority_floor_and_citation_validation(monkeypatch):
    monkeypatch.setattr(ai, "_call_llm", lambda p: fake_output(prio="low"))
    r = run()
    assert r["status"] == "success"
    assert r["ai_output"]["suggested_priority"] == "critical"    
    descs = [c["description"] for c in r["ai_output"]["possible_causes"]]
    assert "Bearing wear" in descs and "Made-up cause" not in descs  # uncited drop
    assert all(c["status"] == "hypothesis" for c in r["ai_output"]["possible_causes"])
    assert r["validation_issues"]

def test_llm_failure_is_partial(monkeypatch):
    def boom(p): raise AIError("timeout")
    monkeypatch.setattr(ai, "_call_llm", boom)
    r = run()
    assert r["status"] == "partial"
    assert r["ai_output"] is None
    assert r["threshold_results"]          # deterministic part still present
    assert "timeout" in r["error"]

def test_retrieval_failure_is_partial():
    r = ai.analyze_report("steam_turbine", "X", "vibration", [], [])
    assert r["status"] == "partial" and "Retrieval failed" in r["error"]