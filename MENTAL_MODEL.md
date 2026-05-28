# Mental Model: Pharma Data Integrity Inspector

## System Overview

A **5-stage AI pipeline** that catches pharma sensor data integrity issues — including sensors that are wrong but look perfectly normal (Cross-Sensor Corroboration). The architecture is **deterministic-first, AI-second**: rules always run (Stage 1), then a genuine ReAct agent investigates (Stage 2), then a human reviews (Stage 3), then AI reasons about root causes (Stage 4) and generates reports (Stage 5).

Only 2 of the 5 stages use LLMs. The Detection Engine is pure deterministic code. The HITL Gate is a human decision. This keeps the system auditable and token-efficient (~3-5K tokens/run).

---

## Architecture

```
Browser (React/Vite/Tailwind, tags state in App.jsx)
    │  axios HTTP calls
    ▼
FastAPI (main.py) ─── PostgreSQL (tags, tag_readings, anomalies, agent_trace)
    │
    ├── /analyze           → Stage 1 (Detection Engine, 9 checks, deterministic)
    │                      → Stage 2 (Investigation Agent, ReAct + 4 tools)
    ├── /anomalies/select  → Stage 3 (HITL approve/reject investigation findings)
    ├── /generate-hypotheses → Stage 4 (Hypothesis Agent, single LLM call) + OutputGuardrail
    ├── /generate-reports  → Stage 5 (Report Generator, LLM narrative) + OutputGuardrail
    ├── /tags/live          → TagSimulator (real-time, 30s interval, random 2-4 anomalies)
    ├── /stats/*            → Correlation matrix, causal groups, integrity checks, tech stack
    │
    └── LangGraph StateGraph (pipeline.py)
        detect → investigate → [HITL gate] → hypothesize → report
```

---

## Data Flow

### 1. Data Generation (Continuous)
```
TagSimulator → 20 tags at 30-sec intervals → PostgreSQL
```
Each tag: `base + causal_coupling_effects + phi*(prev-base) + noise + diurnal`

Random 2-4 anomalies per reseed from 6 templates (no tag overlap):
- **sensor_drift**: gradual offset at 1-5%/hr (or 0.5-2% for slow drift)
- **stuck_value**: frozen at a value for 2-8 hours
- **spike**: sudden 3-8x multiplier for 1-3 data points
- **noise_burst**: 3-8x noise for 1-4 hours
- **silent_lie**: 2-6% offset with Good quality code (the novel fault)
- Hard cap of 4 detected anomalies, dedup by tag_id, priority-sorted

### 2. Analysis Pipeline (User-triggered)
```
User clicks "Start Analysis"
  → Stage 1: 1 bulk SQL query + 9 deterministic checks (no LLM) ~3-4s
  → Stage 2: Per anomaly, ReAct agent decides which of 4 tools to call ~2-3s/anomaly
  → anomalies + investigation findings saved to DB with hitl_status='pending'
  → Stage 3: user reviews AI investigation findings at /hitl page, approves/rejects
  → Stage 4: generates root causes per approved anomaly (single LLM call + guardrail)
  → Stage 5: produces PDF/HTML/JSON reports (LLM narrative + templates + guardrail)
```

### 3. Stage Handoffs
```
Stage 1 output (anomalies) → Stage 2 input (anomalies to investigate)
Stage 2 output (investigation findings) → DB → HITL selection → Stage 4 input (approved only + findings)
Stage 4 output (hypotheses) → DB → Stage 5 input
All handoffs logged to agent_trace table
```

---

## The 9 Active Integrity Checks

| # | Name | Detects | Method | Threshold |
|---|------|---------|--------|-----------|
| 1 | Sensor Drift | Gradual calibration degradation | Rolling mean 1h vs 6h | drift_rate > 1%/hr |
| 2 | Stuck Value | Transmitter stopped updating | Adaptive window, unique count | <3 unique values in 1h window |
| 3 | Impossible Readings | Outside physical possibility | Per-datatype limits | e.g., T < -273°C, P < 0 |
| 4 | Rate-of-Change | Impossible step changes | Delta between consecutive readings | Type-specific, >10 violations |
| 5 | Noise Burst | Sudden noise spikes | Std deviation comparison | >5x baseline std |
| 6 | Correlation Breakdown | Related tags stopped correlating | Split-half Pearson r shift | Shift > 0.8 |
| 7 | CIP Temperature Low | Incomplete cleaning cycle | TI-601 < 70°C | >10 low readings |
| 8 | FDA Audit Trail | 21 CFR Part 11 concern | Quality code distribution | >50% non-Good |
| **9** | **Cross-Sensor Corroboration** | **Sensor PLAUSIBLE but WRONG** | **Segmented correlation + trend direction** | **Corr drop + contradicted trend** |

### Former checks (removed/disabled):
- Quality Code Mismatch (disabled)
- Data Gaps (disabled)
- Statistical Outliers (disabled)

### Check 9 — How It Works

For each suspect tag (e.g., TI-101), we have **witness sensors** (PI-101, FI-201, LI-101) and their **expected relationship** (same/opposite direction, coupling coefficient).

1. Compute baseline correlation (first 3 segments) and recent correlation (last segment)
2. If recent correlation drops significantly from baseline:
   - Check if suspect trend **contradicts** what physics predicts given witness trends
   - Example: TI-101 trending UP but FI-201 (cooling) also trending UP — they should be inversely related
   - This means TI-101 is wrong, because if the reactor were actually hotter, cooling would increase
3. If contradictions found → flag as `cross_sensor_inconsistency` with `is_silent_lie: True`

**Why this is novel:** No historian or analytics tool checks correlated sensors. They check each sensor in isolation (thresholds, quality codes). This is the only check that says "this reading looks fine on its own, but its *witnesses* tell a different story."

8 tags have witness groups: TI-101, PI-101, FI-201, VI-301, TI-202, PI-502, LI-101, TI-601.

---

## The 5 Pipeline Stages

### Stage 1: Detection Engine (`detection_engine.py`)
- **Not an agent.** Pure deterministic code, no LLM.
- 1 bulk SQL query loads ALL readings. 9 rule-based checks on every tag.
- Dedup by tag_id, cap at 4, priority sort.
- Zero LLM tokens. Returns in ~3-4s.
- **agent_name** in traces: `DetectionEngine`

### Stage 2: Investigation Agent (`investigation_agent.py`)
- **Genuine ReAct agent** with `create_react_agent` from LangGraph.
- **4 tools** that query simulated external systems:
  - `query_historian` → PI Historian API (trend data, statistics, correlations)
  - `query_events` → MES API (batch events, CIP cycles, operator actions)
  - `query_maintenance` → CMMS API (calibration history, work orders, sensor replacements)
  - `query_lab_results` → LIMS API (lab samples, batch quality, analytical data)
- **ANOMALY_GUIDANCE** dict tells the LLM which tools are most relevant per anomaly type, but the LLM decides the actual call sequence.
- Different anomaly types lead to genuinely different investigation paths:
  - **Stuck value** → likely `query_maintenance` (broken transmitter?) → `query_historian` (how long stuck?)
  - **Cross-sensor** → likely `query_historian` (trend analysis) → `query_lab_results` (lab confirmation)
  - **CIP temperature low** → likely `query_events` (CIP cycle status) → `query_maintenance` (heater calibration?)
- Captures reasoning + tool calls per anomaly for the trace view.
- **agent_name** in traces: `InvestigationAgent`

### Stage 3: HITL Gate
- **Human-in-the-Loop gate** between Investigation and Hypothesis.
- Human reviews AI investigation findings, not just raw anomalies.
- Prevents AI from generating root causes based on unreviewed evidence.
- FDA 21 CFR Part 11 aligned.

### Stage 4: Hypothesis Agent (`hypothesis_agent.py`)
- **Single LLM call** per anomaly, no tools.
- Receives investigation findings + anomaly details.
- OutputGuardrail validates every hypothesis.
- **agent_name** in traces: `HypothesisAgent`

### Stage 5: Report Generator (`report_generator.py`)
- LLM writes executive narrative.
- ReportLab generates PDF, Jinja2 generates HTML, JSON export.
- Guardrail sanitizes all free-text + blocks dangerous recommendations.
- **agent_name** in traces: `ReportGenerator`

---

## Performance Architecture

### Stage 1 (Detection Engine, no LLM, ~3-4s):
```
1 bulk query ALL readings                       ~1-2s
Compute profiles inline (numpy)                 ~0.1s
9 rule-based checks                             ~0.5s
Dedup + cap + priority sort                     ~0.01s
+ DB inserts:                                   ~1-2s
                                               ≈3-4s total
```

### Stage 2 (Investigation Agent, ReAct, ~2-3s per anomaly):
```
Per anomaly:
  LLM decides tool calls                        ~1-2s
  Tool executions (simulated APIs)              ~0.1s
  LLM processes results                         ~1s
For 2-4 anomalies:                              ~4-12s
```

### Stages 4-5 (LLM calls, ~2-5s each):
```
Stage 4: Single LLM call per approved anomaly   ~2-3s/anomaly
Stage 5: LLM narrative + template rendering      ~3-5s
```

Key design choices:
- **Detection Engine is code, not AI** — zero tokens, 100% coverage, fully auditable
- **ReAct investigation** — LLM decides tool calls, genuine agency
- **Single bulk query** — `_load_all_readings()` replaces N+1 per-tag queries
- **Adaptive windows** — all checks compute window sizes from `86400/n` seconds per sample (works on any interval)
- **30-second seeding** — 2,880 readings/tag instead of 17,280 (still enough for drift/correlation detection)

---

## Output Guardrail (`guardrail.py`)

Three layers, applied to Stages 2, 4, and 5:

| Layer | What | Example |
|-------|------|---------|
| **Redaction** | PII, pharma-sensitive, credentials | `SSN XXX-XX-XXXX` → `[SSN-REDACTED]`, `BATCH-12345` → `[BATCH-REDACTED]`, `password=xyz` → `[CREDENTIAL-REDACTED]` |
| **Blocking** | Dangerous recommendations | "bypass audit trail" → `[GUARDRAIL: This recommendation was blocked]` |
| **Bounding** | Confidence clamping | confidence > 1.0 → 1.0, non-numeric → 0.5 |

---

## HITL (Human-in-the-Loop) Gate

**Position:** Between Investigation (Stage 2) and Hypothesis (Stage 4)

**Why:** AI can hallucinate or over-flag. Before AI generates root causes, a human reviews the investigation findings and approves or rejects anomalies. This gates an AI step (investigation output), not deterministic code.

**Flow:**
1. Stages 1-2 flag anomalies + produce investigation findings → all start as `hitl_status='pending'`
2. Human reviews at `/hitl` page → approves or rejects each
3. Only approved anomalies go to Stage 4
4. Rejected anomalies: no hypothesis generated
5. **All-rejected flow:** Steps 3-4 still accessible; "All anomalies rejected — Continue to Report" shown; reports work with empty anomalies (clean bill of health)

**FDA 21 CFR Part 11 alignment:** This provides the "electronic signature" equivalent — a human made a decision before AI acted on data.

---

## Tag Simulator (`tag_simulator.py`)

5 causal groups with physics-based couplings:

| Group | Tags | Key Coupling | Physics |
|---|---|---|---|
| Reactor R-101 | TI-101, PI-101, FI-101, LI-101 | TI-101→PI-101 (0.05) | Clausius-Clapeyron |
| HX-201 | TI-201, FI-201, TI-202 | TI-201→TI-202 (0.9) | Heat transfer |
| Pump P-301 | PI-301, FI-301, VI-301 | PI-301→FI-301 (20.0) | Pump curve |
| Tank T-401 | TI-401, LI-401, PI-401 | — | — |
| CIP System | TI-601, FI-601, CI-601 | — | — |
| Compressor C-501 | PI-501, PI-502, TI-501 | PI-501→PI-502 (3.0) | Compression ratio |

Cross-group: TI-101→FI-201 (-0.8, "higher temp → more cooling"), FI-101→LI-101 (0.15, "feed raises level")

**Silent Lie injection:** When `silent_lie` is chosen from the pool, the tag's reported value gets an offset (2-6% of base), but the *actual* AR(1) state stays correct. So witness sensors see the real value, making them contradict the reported value.

**AR(1) model:** `value = base + coupling_effects + phi * (prev - base) + noise + diurnal`
- phi = 0.85 (autocorrelation — smooth, not jittery)
- diurnal = sin(hour) amplitude variation
- Deviation from causal prediction is clamped to prevent correlated tags from being flagged as drift

**Seeding:** 30-second intervals → 2,880 readings/tag → ~57,600 total for 20 tags. Startup clears old anomalies and traces before seeding.

---

## Pipeline Orchestration (`pipeline.py`)

LangGraph StateGraph with conditional HITL edge:

```
detect → investigate → route_after_investigation()
                              ↓               ↓
                         hitl_gate          END (no anomalies)
                              ↓
                         hypothesize → report → END
```

**Current implementation:**
- `/analyze` runs `detect_step()` + `investigate_step()` (Stages 1-2)
- Returns anomalies + investigation findings immediately
- Stages 4 and 5 are triggered by separate API calls (`/generate-hypotheses`, `/generate-reports`) after HITL approval
- `/analyze` clears old anomalies + traces before running detection

---

## Frontend Architecture

```
App.jsx (root)
├── State: liveTags, anomalyCount, approvedCount, rejectedCount, hypothesisCount
├── Polling: tags/live + anomalies every 5s (lifted to App level, persists across routes)
├── Header: dark mode toggle, Stats/Trace links, pipeline step nav (data-driven)
├── Routes:
│   / → Dashboard (live sensor grid, 5 stage cards, Cross-Sensor Corroboration card)
│   /anomalies → AnomalyDetection (9 checks grid, anomaly cards, investigation reasoning)
│   /hitl → HITLSelection (approve/reject investigation findings)
│   /hypotheses → HypothesisView (root causes, confidence, actions)
│   /reports → ReportPreview (PDF/HTML/JSON download)
│   /trace → TraceView (Min/Full toggle, stage I/O log)
│   /stats → StatsForNerds (correlation matrix, causal groups, tech stack, FAQ)
└── api.js: VITE_API_BASE env variable (Render in prod, localhost in dev)
```

**State management:** useState + useEffect with 5-sec polling. Tags state lifted to App.jsx to persist across route changes (no flash on navigate back).

**Pipeline step progress:** Steps 0-4 highlight based on state:
- Step 0 (Detect): green when anomalyCount > 0
- Step 1 (Investigate): green when investigation findings exist
- Step 2 (Review): green when all HITL decided
- Step 3 (Hypothesize): green when hypothesisCount > 0, accessible when approvedCount > 0 or all-rejected
- Step 4 (Report): accessible only when hypothesisCount > 0

**Dark mode:** `document.documentElement.classList.toggle('dark')` with localStorage persistence. CSS variables in index.css define both `:root` (light) and `.dark` (navy) palettes.

**All-rejected flow:** Steps 3-4 accessible even with no approvals. HypothesisView shows "All anomalies rejected — Continue to Report." Reports generate with empty anomalies (clean bill of health).

---

## Technology Choices — Why Each

| Tech | Why |
|---|---|
| **LangGraph** | Pipeline is a directed graph with a conditional edge (HITL). StateGraph makes this explicit and traceable. `create_react_agent` from `langgraph.prebuilt` creates the Investigation Agent. |
| **LangChain** | PromptTemplate, ChatOpenAI, `@tool` decorator — standard LLM interface and agent tools. |
| **Groq Llama 3.1 8B Instant** | Fast inference (~2-5s per call), cost-efficient, good enough for pharma domain reasoning. |
| **langchain_openai** v1.2+ | Uses `api_key` and `base_url` (not old `openai_api_key`/`openai_api_base`). Compatible with Groq. |
| **FastAPI** | Async REST API. Pydantic models for request/response validation. |
| **SQLAlchemy 2.0 async** | Async PostgreSQL with `asyncpg` driver for concurrent DB queries. |
| **PostgreSQL JSONB** | `evidence` column stores nested JSON (witness details, correlation values, is_silent_lie). |
| **NumPy/SciPy** | Rolling means, z-scores, Pearson r — all statistical checks are pure numpy/scipy. |
| **React + Vite + Tailwind** | Component UI, fast HMR, utility-first CSS with dark mode. |
| **asyncpg** | Direct async SQL for bulk queries (1 query instead of N+1 per-tag). |

---

## Design Decisions

### 1. "Deterministic-first, AI-second" Pipeline
Rules always run (9 checks on every tag). LLM adds interpretation and investigation on top. This gives 100% check coverage and auditability. The Detection Engine is pure code — no risk of the LLM skipping a check.

### 2. Detection Engine Is NOT an Agent
Calling deterministic code an "agent" is misleading. Stage 1 runs 9 rule-based checks — zero LLM tokens, zero agency. It's a function, not an agent. Only Stages 2 and 4 are genuine AI agents.

### 3. Investigation Agent Is Genuinely ReAct
The old architecture had fake tools (data lookups from in-memory caches, always called in same order). The new Investigation Agent queries 4 simulated external systems (Historian, MES, CMMS, LIMS). Different anomaly types → different tool call sequences. The LLM decides which tools to call and with what parameters.

### 4. Hypothesis Agent Is a Single LLM Call
Not every AI step needs to be an agent. Root cause hypothesis doesn't need tools — it needs focused reasoning from collected evidence. A single LLM call with investigation findings is more token-efficient than a ReAct loop.

### 5. HITL Gates an AI Step, Not Deterministic Code
The human reviews investigation findings (AI output from Stage 2) before hypothesis generation (AI Step 4). This gates AI on AI, not human on code — which is the real value of HITL.

### 6. Single Bulk Query
Instead of `SELECT * FROM tag_readings WHERE tag_id = ?` in a loop (N+1 queries), the Detection Engine uses `_load_all_readings()` — one query that fetches all readings, then groups them in Python.

### 7. Adaptive Window Sizes
All checks compute window sizes from `86400/n` (seconds per sample). This makes them work on any interval — 5s, 30s, 1min — without hardcoded window sizes.

### 8. Random 2-4 Anomalies Per Reseed
Each reseed picks 2-4 random anomalies from a pool of 6 templates, with no tag overlap. This makes the demo more interesting — you get different faults each time. Priority sort ensures cross_sensor_inconsistency > sensor_drift > stuck_value > others.

### 9. Tags State Lifted to App.jsx
Tags were being fetched in Dashboard.jsx and re-fetched on every navigation, causing a flash. Now `liveTags` state lives in App.jsx and persists across routes — no flash on navigate back.

### 10. Guardrail on Output, Not Input
Pharma context means AI output is what reaches operators. Input-side filtering would miss legitimate data that happens to contain batch numbers. Output-side filtering catches PII that the LLM hallucinated.

### 11. Deterministic Silent Lie Injection
The offset is applied to `reported_value` only, not the AR(1) state. This prevents accumulation and ensures witness sensors see the truth.

---

## Deployment

- **Backend:** Render Web Service (Python 3.11.9, uvicorn, PostgreSQL addon, Frankfurt region)
- **Frontend:** Vercel (Vite, env variable `VITE_API_BASE` → Render URL)
- **Database:** Render PostgreSQL (external URL for schema setup from local psql)
- **LLM:** Groq Llama 3.1 8B Instant (via langchain_openai with base_url)
- **Environment variables:** `LLM_API_KEY` (Groq key), `LLM_BASE_URL` (https://api.groq.com/openai/v1), `LLM_MODEL` (llama-3.1-8b-instant)
- **Runtime:** `backend/runtime.txt` specifies `3.11.9`
- **Startup:** Clears old anomalies + traces before seeding fresh data