import json
import logging
import time
from typing import Literal
from pydantic import BaseModel, ValidationError
from google import genai
from google.genai import types

from app.config import settings
from app.rules import run_threshold_checks, overall_severity
from app.rag import retrieve, get_chunks, RetrievalError

log = logging.getLogger("triage.ai")

PRIORITIES = ["low", "medium", "high", "critical"]


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
    """Query-based hits + hamesha limits (x-1.1) aur priority guidance (x-3.2) sections."""
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


def _call_llm(prompt: str) -> AIOutput:
    if not settings.gemini_api_key:
        raise AIError("GEMINI_API_KEY is not configured")

    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=45000),
    )

    last_err = None

    for attempt in (1, 2):
        try:
            resp = client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=AIOutput,
                    temperature=0.2,
                ),
            )

            if not resp.text:
                raise AIError("Empty response from model")

            return AIOutput.model_validate_json(resp.text)

        except (ValidationError, json.JSONDecodeError) as e:
            last_err = AIError(
                f"Model returned invalid structured output: {e}"
            )

        except AIError as e:
            last_err = e

        except Exception as e:
            last_err = AIError(
                f"LLM request failed: {type(e).__name__}: {e}"
            )

        log.warning(
            "llm_attempt_failed attempt=%s error=%s",
            attempt,
            last_err,
        )

        # Give temporary Gemini 503/availability issues time to recover
        if attempt == 1:
            time.sleep(5)

    raise last_err


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

    # Priority AI ke bharose nahi: rules se neeche nahi ja sakti
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
    Kabhi crash nahi karta. status: success | partial | failed
    Deterministic results hamesha milte hain, AI/retrieval fail ho tab bhi.
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
            {"id": c["id"], "title": c["title"], "score": c["score"]} for c in chunks
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