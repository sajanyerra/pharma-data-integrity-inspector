# Mental Model: Pharma Data Integrity Inspector

## System Overview

A **4-agent AI pipeline** that catches pharma sensor data integrity issues — including sensors that are wrong but look perfectly normal (Cross-Sensor Corroboration). The architecture is **deterministic-first, AI-second**: rules always run, LLM adds interpretation on top.

---

## Architecture

```
Browser (React/Vite/Tailwind)
    │  axios HTTP calls
    ▼
FastAPI (main.py) ─── PostgreSQL (tags, tag_readings, anomalies, agent_trace)
    │
    ├── /analyze          → Agent 1 (Data Profiler) + Agent 2 (Anomaly Detector)
    ├── /anomalies/select  → HITL approve/reject
    ├── /generate-hypotheses → Agent 3 (Hypothesis Generator) + OutputGuardrail
    ├── /generate-reports → Agent 4 (Report Generator) + OutputGuardrail
    ├── /tags/live        → TagSimulator (real-time, seed=None)
    ├── /stats/*          → Correlation matrix, causal groups, integrity checks, tech stack
    │
    └── LangGraph StateGraph (pipeline.py)
        profile → detect → [HITL gate] → hypothesize → report
```

---

## Data Flow

### 1. Data Generation (Continuous)
```
TagSimulator → 20 tags at 5-sec intervals → PostgreSQL
```
Each tag: `base + causal_coupling_effects + phi*(prev-base) + noise + diurnal`

3 injected anomalies (deterministic, seed=42):
- **TI-101 sensor_drift**: +2.5°C/hr from hour 10
- **VI-301 stuck_value**: frozen at 4.2 mm/s for 6 hours
- **TI-101 cross_sensor_inconsistency**: -3°C offset on *reported* value (hours 10-14). The actual AR(1) state is correct, so witness sensors (PI-101, FI-201) see the real temperature.

### 2. Analysis Pipeline (User-triggered)
```
User clicks "Start Analysis"
  → Agent 1: profiles tag data (numpy stats + GPT interpretation)
  → Agent 2: runs 11 checks (deterministic rules + GPT prioritization)
  → anomalies saved to DB with hitl_status='pending'
  → HITL: user approves/rejects on /hitl page
  → Agent 3: generates root causes per approved anomaly (GPT + domain KB + guardrail)
  → Agent 4: produces PDF/HTML/JSON reports (GPT narrative + templates + guardrail)
```

### 3. Agent Handoffs
```
Agent 1 output (tag_profiles) → Agent 2 input
Agent 2 output (anomalies) → DB → HITL selection → Agent 3 input (approved only)
Agent 3 output (hypotheses) → DB → Agent 4 input
All handoffs logged to agent_trace table + LangSmith
```

---

## The 11 Integrity Checks

| # | Name | Detects | Method | Key Detail |
|---|------|---------|--------|------------|
| 1 | Sensor Drift | Gradual calibration degradation | Rolling mean 1h vs 6h | drift_rate > 3.5%/hr |
| 2 | Stuck Value | Transmitter stopped updating | Unique count in sliding 720-reading window | <3 unique values |
| 3 | Impossible Readings | Outside physical possibility | Per-datatype limits | e.g., T < -273°C |
| 4 | Quality Code Mismatch | SCADA says Good but data is outlier | IQR outlier % vs Good % | >5% outliers with >90% Good |
| 5 | Rate-of-Change | Impossible step changes | Delta between 5-sec readings | Type-specific thresholds |
| 6 | Data Gaps | Missing historian data | Time delta between readings | Gap > 10 sec (2x scan rate) |
| 7 | Statistical Outliers | Extreme deviations | Z-score | >5σ, >5% of readings |
| 8 | Correlation Breakdown | Related tags stopped correlating | Split-half Pearson r shift | Shift > 0.6 |
| 9 | CIP Temperature Low | Incomplete cleaning cycle | TI-601 < 70°C | >10 low readings |
| 10 | FDA Audit Trail | 21 CFR Part 11 concern | Quality code distribution | >50% non-Good |
| **11** | **Cross-Sensor Corroboration** | **Sensor PLAUSIBLE but WRONG** | **Segmented correlation + trend direction** | **Corr drop > 0.2 + contradicted trend** |

### Check 11 — How It Works

For each suspect tag (e.g., TI-101), we define **witness sensors** (PI-101, FI-201, LI-101) and their **expected relationship** (same/opposite direction, coupling coefficient).

1. Compute baseline correlation (first 3 segments) and recent correlation (last segment)
2. If recent correlation drops > 0.2 from baseline:
   - Check if suspect trend **contradicts** what physics predicts given witness trends
   - Example: TI-101 trending UP but FI-201 (cooling) also trending UP — they should be inversely related
   - This means TI-101 is wrong, because if the reactor were actually hotter, cooling would increase (FI-201 would go UP, not the other way)
3. If contradictions found → flag as `cross_sensor_inconsistency` with `is_silent_lie: True`

**Why this is novel:** No historian or analytics tool checks correlated sensors. They check each sensor in isolation (thresholds, quality codes). This is the only check that says "this reading looks fine on its own, but its *witnesses* tell a different story."

---

## The 4 Agents

### Agent 1: Data Profiler (`data_profiler.py`)
- **Deterministic:** numpy stats (mean, std, min, max, Q1, Q3, quality codes, update frequency, data completeness)
- **AI layer:** GPT-3.5-turbo interprets profiling results, flags data quality concerns
- **Fallback:** Static string if LLM fails
- **Why not just rules?** LLM can say "TI-101 shows 2% data completeness gaps during hours 12-15, which coincides with a CIP cycle — possible SCADA communication issue" which connects dots a rule can't.

### Agent 2: Anomaly Detector (`anomaly_detector.py`)
- **Deterministic:** 11 rule-based checks on every tag
- **AI layer:** GPT-3.5-turbo analyzes the *pattern* of findings across all checks ("3 anomalies in the same reactor unit suggest a systemic issue, not individual sensor failures")
- **Fallback:** Generic summary string
- **Why not just rules?** Rules catch *what*, AI explains *why it matters together*

### Agent 3: Hypothesis Generator (`hypothesis_generator.py`)
- **AI layer:** GPT-3.5-turbo with domain knowledge base per anomaly type
- **Knowledge base:** 11 entries mapping anomaly_type → known root causes + recommended actions (e.g., sensor_drift → "calibration drift due to coating buildup")
- **Guardrail:** OutputGuardrail validates every hypothesis before storage
- **Fallback:** Uses knowledge base entry directly if LLM fails
- **Key detail:** Receives specific tag_id, anomaly_type, evidence per anomaly. LLM is scoped, not free-associating.

### Agent 4: Report Generator (`report_generator.py`)
- **AI layer:** GPT-3.5-turbo writes executive narrative
- **Deterministic:** ReportLab generates PDF, Jinja2 generates HTML, JSON export
- **Guardrail:** Sanitizes all free-text fields
- **Fallback:** Template-based narrative if LLM fails

---

## Output Guardrail (`guardrail.py`)

Three layers, applied to Agent 3 (hypotheses) and Agent 4 (reports):

| Layer | What | Example |
|-------|------|---------|
| **Redaction** | PII, pharma-sensitive, credentials | `SSN XXX-XX-XXXX` → `[SSN-REDACTED]`, `BATCH-12345` → `[BATCH-REDACTED]`, `password=xyz` → `[CREDENTIAL-REDACTED]` |
| **Blocking** | Dangerous recommendations | "bypass audit trail" → `[GUARDRAIL: This recommendation was blocked]` |
| **Bounding** | Confidence clamping | confidence > 1.0 → 1.0, non-numeric → 0.5 |

---

## HITL (Human-in-the-Loop) Gate

**Position:** Between Agent 2 and Agent 3

**Why:** AI can hallucinate or over-flag. Before AI generates root causes, a human reviews and approves/rejects anomalies. This prevents AI from recommending actions based on false alarms.

**Flow:**
1. Agent 2 flags anomalies → all start as `hitl_status='pending'`
2. Human reviews at `/hitl` page → approves or rejects each
3. Only approved anomalies go to Agent 3
4. Rejected anomalies: no hypothesis generated

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

Cross-group: TI-101→FI-201 (-0.8, "higher temp → more cooling"), FI-101→LI-101 (0.15, "feed raises level")

**Silent Lie injection:** TI-101 reported value gets -3°C offset (hours 10-14), but the *actual* state stays correct. So PI-101 and FI-201 see the real temperature, making them "witnesses" that contradict TI-101's reported value.

**AR(1) model:** `value = base + coupling_effects + phi * (prev - base) + noise + diurnal`
- phi = 0.98 (autocorrelation — smooth, not jittery)
- diurnal = sin(hour) amplitude variation
- Deviation from causal prediction is clamped to prevent correlated tags from being flagged as drift

---

## Pipeline Orchestration (`pipeline.py`)

LangGraph StateGraph with conditional HITL edge:

```
profile → detect → route_after_detection()
                         ↓               ↓
                    hitl_gate          END (no anomalies)
                         ↓
                    hypothesize → report → END
```

**Current implementation:** The `/analyze` endpoint runs `profile_step()` + `detect_step()` directly. It does NOT execute the full graph through to hypothesize/report. Agents 3 and 4 are triggered by separate API calls (`/generate-hypotheses`, `/generate-reports`) after HITL approval. This is because the human needs to review between steps.

---

## Database Schema

```sql
tags (tag_id PK, tag_name, unit_type, data_type, normal_min, normal_max, scan_rate_sec, description)
tag_readings (id PK, tag_id FK→tags, timestamp, value, quality_code, created_at)
anomalies (id PK, tag_id FK→tags, anomaly_type, confidence, evidence JSONB, detected_at, hitl_status, hypothesis, recommended_action)
agent_trace (id PK, agent_name, input JSONB, output JSONB, created_at)
```

Key: `evidence` is JSONB — stores correlation values, witness details, `is_silent_lie`, `pharma_impact`, `severity`, `contradictions` list.

---

## Frontend Architecture

```
App.jsx (root)
├── Header: dark mode toggle, Stats/Trace links, pipeline step nav (data-driven from anomaly state)
├── Routes:
│   / → Dashboard (live sensor grid, 4 agent cards, Cross-Sensor Corroboration card)
│   /anomalies → AnomalyDetection (11 checks grid, anomaly cards)
│   /hitl → HITLSelection (approve/reject)
│   /hypotheses → HypothesisView (root causes, confidence, actions)
│   /reports → ReportPreview (PDF/HTML/JSON download)
│   /trace → TraceView (Min/Full toggle, agent I/O log)
│   /stats → StatsForNerds (correlation matrix, causal groups, tech stack, FAQ)
└── api.js: VITE_API_BASE env variable (Render in prod, localhost in dev)
```

**State management:** useState + useEffect with 5-sec polling. No Zustand/TanStack Query in current version (QueryClient was imported but pages use plain axios).

**Dark mode:** `document.documentElement.classList.toggle('dark')` with localStorage persistence. CSS variables in index.css define both `:root` (light) and `.dark` (navy) palettes.

---

## Technology Choices — Why Each

| Tech | Why |
|---|---|
| **LangGraph** | Pipeline is a directed graph with a conditional edge (HITL). StateGraph makes this explicit and traceable. |
| **LangChain** | PromptTemplate, ChatOpenAI, JsonOutputParser — standard LLM interface. |
| **LangSmith** | Traces every LLM call for debugging and FDA audit. EU endpoint for data residency. |
| **GPT-3.5-turbo** | Cost-efficient for demo (~500-1000 tokens/call × 4 agents = ~$0.01/run). GPT-4o for production. |
| **FastAPI** | Async REST API. Pydantic models for request/response validation. |
| **SQLAlchemy 2.0 async** | Async PostgreSQL with `asyncpg` driver for concurrent DB queries in agents. |
| **PostgreSQL JSONB** | `evidence` column stores nested JSON (witness details, correlation values, is_silent_lie). |
| **NumPy/SciPy** | Rolling means, z-scores, Pearson r — all statistical checks are pure numpy/scipy. |
| **React + Vite + Tailwind** | Component UI, fast HMR, utility-first CSS with dark mode. |
| **asyncpg** | Direct async SQL for correlation queries (heavy JOINs). |

---

## Design Decisions

### 1. "Deterministic-first, AI-second" Agent Pattern
Rules always run (11 checks on every tag). LLM adds interpretation on top. This gives 100% check coverage and auditability. A "true agent" with tool calling would be more flexible but less predictable — the LLM might forget to run an important check.

**Evolution path:** Add tool calling to Agent 2 for efficiency (LLM decides which correlating tags to investigate deeper) while keeping the 11 mandatory checks as a baseline.

### 2. HITL Before Agent 3, Not After
Review before AI generates root causes. Cheaper (no wasted LLM calls on false alarms) and safer (AI doesn't act on unreviewed data).

### 3. Guardrail on Output, Not Input
Pharma context means AI output is what reaches operators. Input-side filtering would miss legitimate data that happens to contain batch numbers. Output-side filtering catches PII that the LLM hallucinated.

### 4. Deterministic Silent Lie Injection
The -3°C offset is applied to `reported_value` only, not the AR(1) state. This prevents accumulation and ensures witness sensors see the truth.

### 5. Causal Tag Simulator (Not Random Noise)
Correlated tags follow physics (Clausius-Clapeyron, mass balance, pump curves). Random noise wouldn't produce realistic correlation patterns for Check 8 and Check 11 to analyze.

---

## Deployment

- **Backend:** Render Web Service (Python 3.11.9, uvicorn, PostgreSQL addon)
- **Frontend:** Vercel (Vite, env variable `VITE_API_BASE` → Render URL)
- **Database:** Render PostgreSQL (external URL for schema setup from local psql)
- **LLM:** OpenAI GPT-3.5-turbo (API key in env)
- **Tracing:** LangSmith EU endpoint