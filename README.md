# Equipment Maintenance Triage Assistant

A technician reports an equipment problem (type, identifier, issue, recent operating events, optional sensor readings). The system runs **deterministic threshold checks**, retrieves relevant **manual sections** (BM25), asks an **LLM** for hypotheses, follow-up questions, inspection steps, a priority and a draft work order, then **validates every citation and the priority in code**. A technician can edit, approve or reject the draft. The AI never approves work or controls equipment.

- **Live app:** https://equipment-triage.vercel.app
- **API (FastAPI docs):** https://equipment-triage-api.onrender.com/docs
- **Repo:** https://github.com/HARNOOR2004/equipment-triage

> Hosting note: the API runs on a free Render instance and the LLM is a free OpenRouter model. The first request after idle can take ~50 s (cold start) and an analysis can take 30-60 s. The UI shows loading states and a retry button.

## Architecture

```
React (Vite, Vercel)  --HTTP/JSON-->  FastAPI (Render)  -->  PostgreSQL (Neon)
                                         |
                    +--------------------+---------------------+
                    |                    |                     |
              rules.py              rag.py (BM25)          ai.py (LLM)
         deterministic checks     manual sections       OpenRouter call +
         missing/invalid/conflict  from backend/kb/      citation validation +
                                                         priority floor
```

Analysis pipeline (`app/ai.py::analyze_report`), in order:

1. **Threshold checks** (`rules.py`): per-sensor status `normal | warning | critical | missing | invalid | conflict`. Always computed, never by the LLM.
2. **Retrieval** (`rag.py`): BM25 over `## [ID] Title` sections of the manuals in `backend/kb/`, filtered by equipment type. The limits section (`*-1.1`) and priority guidance (`*-3.2`) are always included.
3. **LLM call**: prompt contains the issue, events (`E1..En`), threshold results (`SENSOR:<name>`) and manual sections. Output is requested as JSON matching a Pydantic schema.
4. **Validation** (code, not the LLM):
   - citations must be a retrieved manual section ID, an event ID, or `SENSOR:<name>`; unknown references are removed
   - causes and steps left without any valid citation are dropped
   - every cause is stored with status `hypothesis`
   - the AI priority can never be below the rule-based floor (critical reading -> critical; 2+ warnings -> high; 1 warning -> medium). Raising is logged in `validation_issues`.
5. **Persistence**: analysis, draft work order (`status=draft`), findings and an audit log row.

### Observation vs possible cause vs confirmed finding

| Kind | Where it lives | Who writes it |
|---|---|---|
| Observation | `findings` (kind `observation`) and threshold results | technician / rules |
| Possible cause | `analyses.ai_output.possible_causes`, always labelled "Hypothesis" in the UI | AI (validated) |
| Confirmed finding | `findings` (kind `confirmed`) | technician only |

### Missing / conflicting data

- no reading -> `missing` ("not assumed normal")
- two readings for one sensor that differ by more than 10% -> `conflict`, not evaluated
- value outside a plausible range, wrong unit, or sensor without a rule -> `invalid`
- the overall severity becomes `uncertain` if nothing is critical/warning but data is missing/invalid/conflicting
- the LLM is told to describe these in `data_quality_notes`, and the UI shows them in a warning banner

### Failure handling

`analyze_report` never raises. If retrieval or the LLM fails (timeout, rate limit, invalid JSON, empty response, missing config), the analysis is saved with `status=partial` and an error message. The UI shows an amber banner with the exact error, the deterministic threshold table, the retrieved manual sections and a **Retry analysis** button. The LLM call is retried once (not on timeouts).

### Human review

- AI output is stored as a **draft** work order. Only a technician can approve or reject it.
- Draft fields (title, description, priority, steps) are editable until approval. Approved/rejected orders are locked.
- Approving with a priority **below the rule-based floor** is rejected by the API (HTTP 422) unless an `override_reason` is given; the reason is stored in the audit log.
- Rejection requires a reason. Reviewer name and time are stored.
- Re-analysis (e.g. after follow-up answers) marks the previous draft `superseded` and creates a new draft. History is kept.

## Repository layout

```
backend/
  app/
    main.py        FastAPI app, CORS, logging, /health
    routes.py      REST endpoints
    schemas.py     request models
    models.py      SQLAlchemy models (equipment, reports, sensor_readings, analyses,
                   findings, work_orders, audit_log)
    rules.py       thresholds and deterministic checks
    rag.py         BM25 retrieval over the knowledge base
    ai.py          LLM call, citation validation, priority floor, failure handling
    config.py      settings from environment
  kb/              centrifugal_pump.md, air_compressor.md, conveyor_motor.md
  tests/           test_rules.py, test_rag.py, test_ai.py, test_api.py
frontend/          Vite + React app (hash routing, no router dependency)
```

## API summary

| Method | Path | Purpose |
|---|---|---|
| GET | `/equipment-types` | supported types and their sensors/units |
| POST | `/reports` | create report (creates equipment record if new) |
| GET | `/reports`, `/reports/{id}` | list / detail (analyses, work orders, findings) |
| POST | `/reports/{id}/analyze` | run threshold checks + retrieval + LLM; body `{answers: {question: answer}}` |
| POST | `/reports/{id}/findings` | technician adds an `observation` or `confirmed` finding |
| GET | `/equipment/{identifier}/history` | full history for one equipment |
| PATCH | `/work-orders/{id}` | edit a draft |
| POST | `/work-orders/{id}/approve` | approve (optional `override_reason`) |
| POST | `/work-orders/{id}/reject` | reject (`reason` required) |

The technician name is sent in the `X-Technician` header (typed into the UI header).

## Local setup

Requirements: Python 3.12+, Node 18+, a PostgreSQL database (e.g. Neon), an OpenRouter API key.

```powershell
# backend
cd backend
python -m venv ..\.venv
..\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # then fill in values
uvicorn app.main:app --reload

# frontend (second terminal)
cd frontend
copy .env.example .env
npm install
npm run dev                 # http://localhost:5173
```

### Configuration

| Variable | Where | Meaning |
|---|---|---|
| `DATABASE_URL` | backend | SQLAlchemy URL, e.g. `postgresql+psycopg2://user:pass@host/db?sslmode=require` |
| `OPENROUTER_API_KEY` | backend | OpenRouter key |
| `OPENROUTER_MODEL` | backend | model ID of a free model on OpenRouter (an NVIDIA Nemotron model is used in the deployment) |
| `CORS_ORIGINS` | backend | comma-separated allowed origins (frontend URL) |
| `VITE_API_URL` | frontend | backend base URL |

Tables are created on startup (`create_all`). No secrets are committed; see the `.env.example` files.

## Tests

```powershell
cd backend
python -m pytest
```

12 tests, no network and no real database needed (the LLM is mocked, API tests use in-memory SQLite):

- `test_rules.py`: critical / missing / conflict / invalid-value handling
- `test_rag.py`: retrieval relevance, unknown equipment type, no-match error
- `test_ai.py`: priority floor override, uncited-cause removal, hypothesis labelling, LLM failure -> partial, retrieval failure -> partial
- `test_api.py`: request validation, draft never auto-approved, floor applied, approve needs override reason when priority is lowered, reject needs a reason, history preserved, approved orders are locked

## Deployment

- **Backend:** Render web service, root directory `backend`, build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check `/health`. Environment variables as in the table above.
- **Database:** Neon PostgreSQL.
- **Frontend:** Vercel, root directory `frontend`, `VITE_API_URL` set to the Render URL.
- **Logging:** structured logs from `triage.ai` (`llm_attempt`, `llm_attempt_failed`, `validation_issues`, `analysis_done`, `retrieval_failed`, `llm_failed`) are visible in the Render log stream.

## Scope

**Included:** report intake with validation, deterministic threshold checks, BM25 retrieval over three manuals, LLM triage with citations, follow-up questions and re-analysis, priority proposal with a rule-based floor, draft work order with edit/approve/reject, observation / hypothesis / confirmed separation, equipment and report history, audit log, loading / empty / validation / success / failure states.

**Excluded (by design):** live IoT integration, predictive maintenance models, inventory management, technician dispatch, authentication, remote equipment control, automatic approval.

## Known limitations

- No authentication: the technician name is a free-text header, so it is not a security control.
- Citation validation checks that a reference exists and was provided; it does not prove the cited text supports the claim. Technician review is the final check.
- Free LLM: latency is variable (30-60 s) and rate limits can cause a `partial` result; use Retry.
- Render free tier cold starts (~50 s on the first request).
- The BM25 index is rebuilt per query (fine for three small manuals, not for large corpora).
- Sensors are limited to a fixed set per equipment type; thresholds live in code (`rules.py`) and are mirrored in the manuals.
- No migrations tool (tables via `create_all`); the audit log is stored but has no UI.

## Sample inputs for reviewers

The "New report" page has three one-click samples:

1. **Pump P-101**: vibration 7.5 mm/s (critical), temperature 82 C (warning), pressure 8.2 bar
2. **Compressor C-204**: two temperature readings (98 and 112) -> `conflict`
3. **Conveyor M-12**: only current is provided -> other sensors `missing`