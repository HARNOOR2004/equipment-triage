import json
import logging
import time
import httpx
from typing import Literal
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.rules import run_threshold_checks, overall_severity
from app.rag import retrieve, get_chunks, RetrievalError

log = logging.getLogger("triage.ai")

PRIORITIES = ["low", "medium", "high", "critical"]
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


# ---------- Output schema ----------
class Cause(BaseModel):
    description: str
    likelihood: Literal["low", "medium", "high"]
    evidence_refs: list[str]

class Question(BaseModel):
    question: str
    reason: str

class Step(BaseModel):
    instruction: str
    evidence_refs: list[str]

class WorkOrderDraft(BaseModel):
    title: str
    description: str
    priority: Literal["low", "medium", "high", "critical"]
    steps: list[str]

class AIOutput(BaseModel):
    possible_causes: list[Cause]
    follow_up_questions: list[Question]
    inspection_steps: list[Step]
    suggested_priority: Literal["low", "medium", "high", "critical"]
    priority_reasoning: str
    priority_evidence_refs: list[str]
    draft_work_order: WorkOrderDraft
    data_quality_notes: list[str]


class AIError(Exception):
    pass


class AITimeout(AIError):
    pass


SYSTEM_PROMPT = """You are a maintenance triage assistant supporting a human technician.
Rules:
- Possible causes are HYPOTHESES only. Never state a cause as confirmed or certain.
- Use ONLY the manual sections, operating events and sensor results provided. Do not invent facts, limits or procedures.
- Every possible cause, inspection step and the priority MUST cite evidence in evidence_refs using only these reference formats:
  manual section IDs (e.g. PUMP-2.1), event IDs (e.g. E1), or SENSOR:<sensor_name> for sensor check results.
- If sensor data is missing, invalid or conflicting, say so in data_quality_notes. Never assume a missing reading is normal.
- Ask follow-up questions that would help narrow down the cause. Keep them specific.
- Priority must follow the manual's priority guidance.
- You cannot control equipment or approve work. The work order is a DRAFT for a technician to edit, approve or reject.
- Output must match the JSON schema exactly."""


# ---------- Helpers ----------
def _priority_floor(threshold_results: list[dict]) -> str:
    statuses = [r["status"] for r in threshold_results]
    if "critical" in statuses:
        return "critical"
    if statuses.count("warning") >= 2:
        return "high"
    if statuses.count("warning") == 1:
        return "medium"
    return "low"


def _gather_chunks(equipment_type: str, query: str) -> list[dict]:
    """Query-based hits + always the limits (x-1.1) and priority guidance (x-3.2) sections."""
    hits = retrieve(equipment_type, query, k=4)
    ids = {h["id"] for h in hits}
    for c in get_chunks():
        if c["equipment_type"] == equipment_type and (c["id"].endswith("-1.1") or c["id"].endswith("-3.2")):
            if c["id"] not in ids:
                hits.append({**c, "score": 0.0})
                ids.add(c["id"])
    return hits


def _build_prompt(equipment_type, identifier, issue, events, threshold_results, chunks, answers) -> str:
    manual = "\n\n".join(f"[{c['id']}] {c['title']}\n{c['text']}" for c in chunks)
    ev = "\n".join(f"[{e['id']}] {e['text']}" for e in events) or "(none provided)"
    th = "\n".join(
        f"[SENSOR:{r['sensor']}] status={r['status']} value={r['value']} {r['unit'] or ''} | {r['message']}"
        for r in threshold_results
    )
    ans = "\n".join(f"Q: {q}\nA: {a}" for q, a in (answers or {}).items()) or "(none yet)"
    return f"""EQUIPMENT: {equipment_type} ({identifier})

ISSUE DESCRIPTION:
{issue}

RECENT OPERATING EVENTS:
{ev}

DETERMINISTIC THRESHOLD CHECK RESULTS (computed by rules, not by you):
{th}

TECHNICIAN ANSWERS TO EARLIER FOLLOW-UP QUESTIONS:
{ans}

RELEVANT MANUAL SECTIONS:
{manual}
"""


# ---------- LLM call (OpenRouter) ----------
def _parse_output(text: str) -> AIOutput:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.lower().startswith("json"):
            t = t[4:].strip()
    return AIOutput.model_validate_json(t)


def _call_openrouter_once(prompt: str) -> AIOutput:
    schema = json.dumps(AIOutput.model_json_schema())
    system = (
        SYSTEM_PROMPT
        + "\n\nReturn ONLY a JSON object (no markdown, no commentary) that validates against this JSON schema:\n"
        + schema
    )
    payload = {
        "model": settings.openrouter_model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=60) as c:
            r = c.post(OPENROUTER_URL, headers=headers, json=payload)
            if r.status_code == 400:  # some models reject response_format
                payload.pop("response_format")
                r = c.post(OPENROUTER_URL, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        if data.get("error") or not data.get("choices"):
            detail = str(data.get("error") or data)[:300]
            raise AIError(f"Model returned no completion: {detail}")

        text = data["choices"][0].get("message", {}).get("content")
        if not text:
            raise AIError("Model returned an empty message")
        return _parse_output(text)

    except AIError:
        raise
    except httpx.TimeoutException as e:
        raise AITimeout(f"LLM request timed out: {type(e).__name__}")
    except (ValidationError, json.JSONDecodeError) as e:
        raise AIError(f"Model returned invalid structured output: {e}")
    except Exception as e:
        raise AIError(f"LLM request failed: {type(e).__name__}: {e}")


def _call_llm(prompt: str) -> AIOutput:
    if not (settings.openrouter_api_key and settings.openrouter_model):
        raise AIError("LLM is not configured (set OPENROUTER_API_KEY and OPENROUTER_MODEL)")

    last_err = None
    for attempt in (1, 2):
        try:
            log.info("llm_attempt attempt=%s model=%s", attempt, settings.openrouter_model)
            return _call_openrouter_once(prompt)
        except AITimeout as e:
            last_err = e
            log.warning("llm_attempt_failed attempt=%s error=%s (no retry on timeout)", attempt, e)
            break
        except AIError as e:
            last_err = e
            log.warning("llm_attempt_failed attempt=%s error=%s", attempt, e)
            if attempt == 1:
                time.sleep(3)
    raise last_err


# ---------- Validation ----------
def _validate_and_reconcile(out: AIOutput, allowed_refs: set[str], floor: str) -> tuple[dict, list[str]]:
    issues: list[str] = []

    def clean_refs(refs: list[str], label: str) -> list[str]:
        good = [r for r in refs if r in allowed_refs]
        bad = [r for r in refs if r not in allowed_refs]
        if bad:
            issues.append(f"{label}: removed unknown citations {bad}")
        return good

    causes = []
    for c in out.possible_causes:
        refs = clean_refs(c.evidence_refs, f"cause '{c.description[:40]}'")
        if not refs:
            issues.append(f"Dropped uncited cause: '{c.description[:60]}'")
            continue
        causes.append({**c.model_dump(), "evidence_refs": refs, "status": "hypothesis"})

    steps = []
    for s in out.inspection_steps:
        refs = clean_refs(s.evidence_refs, f"step '{s.instruction[:40]}'")
        if not refs:
            issues.append(f"Dropped uncited step: '{s.instruction[:60]}'")
            continue
        steps.append({**s.model_dump(), "evidence_refs": refs})

    prio_refs = clean_refs(out.priority_evidence_refs, "priority")

    # Priority can never go below the deterministic rule-based floor
    ai_prio = out.suggested_priority
    final = ai_prio
    if PRIORITIES.index(ai_prio) < PRIORITIES.index(floor):
        final = floor
        issues.append(f"Priority raised from '{ai_prio}' to '{floor}' by deterministic threshold rules")

    wo = out.draft_work_order.model_dump()
    wo["priority"] = final

    result = {
        "possible_causes": causes,
        "follow_up_questions": [q.model_dump() for q in out.follow_up_questions],
        "inspection_steps": steps,
        "suggested_priority": final,
        "ai_original_priority": ai_prio,
        "priority_reasoning": out.priority_reasoning,
        "priority_evidence_refs": prio_refs,
        "draft_work_order": wo,
        "data_quality_notes": out.data_quality_notes,
    }
    return result, issues


# ---------- Orchestrator ----------
def analyze_report(equipment_type: str, identifier: str, issue: str,
                   events: list[dict], readings: list[dict],
                   answers: dict | None = None) -> dict:
    """
    Never raises. status: success | partial
    Deterministic results are always returned, even when retrieval or the LLM fails.
    """
    threshold_results = run_threshold_checks(equipment_type, readings)
    severity = overall_severity(threshold_results)
    result = {
        "status": "success",
        "severity": severity,
        "threshold_results": threshold_results,
        "retrieved_chunks": [],
        "ai_output": None,
        "validation_issues": [],
        "error": None,
    }

    # 1) Retrieval
    query = issue + " " + " ".join(e["text"] for e in events)
    try:
        chunks = _gather_chunks(equipment_type, query)
        result["retrieved_chunks"] = [
            {"id": c["id"], "title": c["title"], "score": c["score"], "text": c["text"]} for c in chunks
        ]
    except RetrievalError as e:
        log.error("retrieval_failed error=%s", e)
        result["status"] = "partial"
        result["error"] = f"Retrieval failed: {e}. AI suggestions unavailable; threshold results shown."
        return result

    # 2) LLM
    prompt = _build_prompt(equipment_type, identifier, issue, events, threshold_results, chunks, answers)
    try:
        out = _call_llm(prompt)
    except AIError as e:
        log.error("llm_failed error=%s", e)
        result["status"] = "partial"
        result["error"] = f"AI analysis failed: {e}. Threshold results and manual sections shown."
        return result

    # 3) Validate citations + reconcile priority
    allowed = {c["id"] for c in chunks}
    allowed |= {e["id"] for e in events}
    allowed |= {f"SENSOR:{r['sensor']}" for r in threshold_results}
    ai_output, issues = _validate_and_reconcile(out, allowed, _priority_floor(threshold_results))
    result["ai_output"] = ai_output
    result["validation_issues"] = issues
    if issues:
        log.warning("validation_issues count=%s issues=%s", len(issues), issues)
    log.info("analysis_done severity=%s chunks=%s causes=%s",
             severity, len(chunks), len(ai_output["possible_causes"]))
    return result