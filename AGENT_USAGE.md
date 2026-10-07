# Agent Usage

## Tools

- **Claude (chat interface)**: planning, code generation for backend, tests and frontend, debugging from pasted logs and screenshots.
- **Runtime LLM in the product**: a free NVIDIA Nemotron model through OpenRouter, called from `backend/app/ai.py`.
- **Other tooling**: VS Code, pytest, uvicorn, Render / Vercel / Neon dashboards.

## How work was split

| Delegated to the agent (then reviewed and run by me) | Done / decided by me |
|---|---|
| Architecture proposal and build order | Final scope and what to exclude |
| Threshold engine, DB models, routes, schemas | Running every step locally, pasting errors back |
| Knowledge base manuals (3 files) with the `## [ID]` format | Choosing the LLM provider and model after several attempts |
| BM25 retrieval, citation validator, priority floor | Deciding to remove Gemini and keep one provider |
| React frontend (Vite) and CSS | Deployment setup (Render, Vercel, Neon), env vars |
| Test files (12 tests) | Final end-to-end testing on the deployed URL |

## Representative prompts

Prompts I gave the agent while building (paraphrased):

1. "I have to build this from scratch (pasted the problem statement). Tell me what to do, step by step."
2. "Tests pass and pushed. Now KB + retrieval." / "Done up to here, what next?" (iterative, one step at a time, pasting terminal output after each step)
3. "Tests are failing with `No module named fastapi`" (pasted pytest/uvicorn output) -> dependency fix.
4. "Frontend shows 'Cannot reach the server'" (screenshot + uvicorn log) -> CORS fix.
5. "Gemini fails every time, just replace it" -> switched to OpenRouter as the only provider.
6. "Deployed on Render/Vercel, how do I set env vars / which URL goes in CORS?" (screenshots) -> deployment steps.

Prompt used **inside the product** (`SYSTEM_PROMPT` in `ai.py`), summarised:

- possible causes are hypotheses only, never confirmed
- use only the provided manual sections, events and sensor results; do not invent limits or procedures
- every cause, step and the priority must cite evidence using only `PUMP-2.1`-style section IDs, event IDs (`E1`) or `SENSOR:<name>`
- missing / invalid / conflicting sensor data must be reported in `data_quality_notes`, never assumed normal
- follow the manual's priority guidance; output is a draft work order for a human to approve
- output must match the JSON schema (the schema is appended to the prompt)

## Model selection history (what I tried)

1. Started with **Gemini 2.5 flash** through the Google SDK with a response schema. It did not work for my key, so I changed `GEMINI_MODEL` in `.env` to a newer Gemini flash model.
2. The newer Gemini model worked but returned **HTTP 503 "high demand"** during testing. The app handled it correctly (analysis shown as `partial`, thresholds still visible), which gave me a real failure-state test. I added a retry.
3. I wrote a script to list/test the models available to my key and looked for free alternatives. The OpenRouter free list had no Gemini models, so I shortlisted larger free models (Gemma 4 31B, NVIDIA Nemotron 3 Super) and picked **NVIDIA Nemotron**.
4. First I kept Gemini as the primary with OpenRouter as fallback. Because Gemini kept failing, I made OpenRouter the primary, and then **removed Gemini completely** so the code has one provider and no dead path.
5. Trade-off accepted: a free model is slower (30-60 s per analysis) and can be rate-limited; its output is not trusted blindly because citations and priority are validated in code.

## Important agent mistakes and how I caught them

1. **`requirements.txt` was UTF-16.** Redirecting `pip freeze` in PowerShell produced a UTF-16 file that would have failed `pip install -r` on Render. Caught by reading the generated file before deploying; regenerated as UTF-8. It also contained unused packages (`pgvector`), which I removed.
2. **Missing `cors_origins` setting.** The agent's `main.py` used `settings.cors_origins` but its `config.py` snippet did not define it -> `AttributeError` during test collection. Fixed in `config.py`.
3. **Wrong local CORS origin.** The default allowed `localhost:3000` but Vite runs on `5173`, so the browser's preflight got `400` and the UI showed "Cannot reach the server". Found from the uvicorn log (`OPTIONS ... 400`).
4. **Missing `import httpx` in the OpenRouter code.** All tests passed because they mock `_call_llm`, so the real provider code never ran. The first real analysis failed with `NameError: name 'httpx' is not defined`. Lesson: mocked tests do not cover the provider call; I verified it with a real call.
5. **Unhandled OpenRouter error body.** A `200 OK` response without `choices` raised a bare `KeyError: 'choices'` and hid the real reason. I had the code check for an `error` object / empty completion and surface the provider's message.
6. **Stale `.env` loading.** Changing `.env` does not trigger uvicorn `--reload`, which caused confusion during provider testing; I restart the backend after env changes. `Settings` now uses `extra="ignore"` so leftover variables do not crash startup.

## Suggestions I rejected or deliberately did not build

- Vector embeddings / pgvector for retrieval: BM25 over three small manuals is simpler, deterministic and easy to test; the unused dependency was removed.
- Authentication / user accounts: out of scope for the task; documented as a limitation instead.
- Letting the LLM decide the final priority: rejected in favour of a deterministic floor the AI cannot go below.
- Trusting model citations as returned: rejected; unknown references are stripped and uncited causes/steps are dropped.

## How I verified the output

- **Automated (12 tests):** rules (critical / missing / conflict / invalid), retrieval (relevance, unknown type, no match), AI pipeline with a mocked LLM (priority floor raised from `low` to `critical`, fabricated citation removed, causes labelled `hypothesis`, LLM failure and retrieval failure both return `partial` with deterministic results), API (validation errors, draft never auto-approved, approval needs an override reason when priority is lowered, rejection needs a reason, locked after approval, history kept).
- **Real LLM, end to end (local and deployed):** submitted the pump sample, checked the threshold table (vibration critical, temperature warning, pressure normal), hypotheses with citation chips opening the cited manual text, follow-up questions, priority, and the draft work order.
- **Failure states observed for real:** Gemini `503` produced the `partial` banner with the exact error and the threshold table still visible; a missing-`choices` response and the `NameError` showed up as readable errors instead of crashing the request.
- **Deployed check:** Render `/health` returns DB connected; the Vercel frontend talks to the Render API after adding the Vercel origin to `CORS_ORIGINS`.
- **Manual review of AI-generated code:** I read each generated file before committing, and checked `git status` so `.env` and helper scripts were not committed.