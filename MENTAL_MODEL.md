# Mental Model: Pharma Data Integrity Inspector

## System Overview

A **3-agent AI pipeline** that catches pharma sensor data integrity issues — including sensors that are wrong but look perfectly normal (Cross-Sensor Corroboration). The architecture is **deterministic-first, AI-second**: rules always run, LLM adds interpretation on top. Performance-critical detection returns in ~5-8s thanks to merged profiling, single-query data loading, and async LLM calls.

---

## Architecture

```
Browser (React/Vite/Tailwind, tags state in App.jsx)
    │  axios HTTP calls
    ▼
FastAPI (main.py) ─── PostgreSQL (tags, tag_readings, anomalies, agent_trace)
    │
    ├── /analyze           → Agent 2 (Anomaly Detector, profiles inline + 9 checks + async LLM)
    ├── /anomalies/select  → HITL approve/reject
    ├── /generate-hypotheses → Agent 3 (Hypothesis Generator) + OutputGuardrail
    ├── /generate-reports  → Agent 4 (Report Generator) + OutputGuardrail
    ├── /tags/live          → TagSimulator (real-time, 30s interval, random 2-4 anomalies)
    ├── /stats/*            → Correlation matrix, causal groups, integrity checks, tech stack
    │
    └── LangGraph StateGraph (pipeline.py)
        detect → [HITL gate] → hypothesize → report
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
  → Agent 2: 1 bulk SQL query + inline profile computation + 9 checks + async LLM
  → anomalies saved to DB with hitl_status='pending' (returns in ~5-8s)
  → HITL: user approves/rejects on /hitl page
  → Agent 3: generates root causes per approved anomaly (LLM + domain KB + guardrail)
  → Agent 4: produces PDF/HTML/JSON reports (LLM narrative + templates + guardrail)
```

### 3. Agent Handoffs
```
Agent 2 output (anomalies + tag_profiles) → DB → HITL selection → Agent 3 input (approved only)
Agent 3 output (hypotheses) → DB → Agent 4 input
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

## The 3 Agents (was 4, Agent 1 merged into Agent 2)

### Agent 2: Anomaly Detector (`anomaly_detector.py`)
- **Was:** Agent 1 profiled data, then Agent 2 detected anomalies. Now merged.
- **Deterministic:** 1 bulk SQL query loads ALL readings. Profiles (mean, std, min, max, Q1, Q3, quality codes) computed inline from numpy.
- **9 rule-based checks** on every tag, then dedup by tag_id, cap at 4, priority sort.
- **AI layer:** Llama 3.1 8B analyzes the pattern of findings. Runs **async** via `asyncio.ensure_future` — detection returns fast, LLM text updates later.
- **Fallback:** Generic summary string if LLM fails or times out.
- **Performance:** Single `_load_all_readings()` query instead of per-tag loops. Profiles computed from same cache. Adaptive windows from `86400/n`.

### Agent 3: Hypothesis Generator (`hypothesis_generator.py`)
- **AI layer:** Llama 3.1 8B with domain knowledge base per anomaly type
- **Knowledge base:** 9 entries mapping anomaly_type → known root causes + recommended actions
- **Guardrail:** OutputGuardrail validates every hypothesis before storage
- **Fallback:** Uses knowledge base entry directly if LLM fails
- **Key detail:** Receives specific tag_id, anomaly_type, evidence per anomaly. LLM is scoped, not free-associating.
- **All-rejected flow:** Falls back to non-rejected anomalies if none approved.

### Agent 4: Report Generator (`report_generator.py`)
- **AI layer:** Llama 3.1 8B writes executive narrative
- **Deterministic:** ReportLab generates PDF, Jinja2 generates HTML, JSON export
- **Guardrail:** Sanitizes all free-text fields + blocks dangerous recommendations
- **Works with empty anomalies:** Clean bill of health report if all rejected.

---

## Performance Architecture

### Before (sequential, ~30s):
```
Agent 1: DataProfiler (1 query/tag + LLM call)      ~15-20s
Agent 2: AnomalyDetector (1 query/tag + LLM call)    ~10-15s
Total:                                               ~30s
```

### After (merged + async, ~5-8s):
```
Agent 2: AnomalyDetector
  ├── 1 bulk query ALL readings                       ~1-2s
  ├── Compute profiles inline (numpy)                 ~0.1s
  ├── 9 rule-based checks                             ~0.5s
  ├── Dedup + cap + priority sort                     ~0.01s
  ├── Return anomalies immediately                    ~0.01s
  └── LLM prioritization (async, non-blocking)        ~2-5s (background)
Total detection:                                     ~3-4s
+ DB inserts:                                        ~1-2s
                                                     ≈5-8s total
```

Key changes:
- **Merged Agent 1 into Agent 2** — profiles computed inline from same data_cache, no separate DB pass
- **Single bulk query** — `_load_all_readings()` replaces N+1 per-tag queries
- **Async LLM** — detection returns immediately, LLM prioritization updates later via `asyncio.ensure_future`
- **Adaptive windows** — all checks compute window sizes from `86400/n` seconds per sample (works on any interval)
- **30-second seeding** — 2,880 readings/tag instead of 17,280 (still enough for drift/correlation detection)

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
detect → route_after_detection()
              ↓               ↓
         hitl_gate          END (no anomalies)
              ↓
         hypothesize → report → END
```

**Current implementation:**
- `/analyze` runs `detect_step()` only (Agent 2, which includes inline profiling)
- Returns anomalies + tag_profiles immediately (~5-8s)
- Agents 3 and 4 are triggered by separate API calls (`/generate-hypotheses`, `/generate-reports`) after HITL approval
- `/analyze` clears old anomalies + traces before running detection

---

## Frontend Architecture

```
App.jsx (root)
├── State: liveTags, anomalyCount, approvedCount, rejectedCount, hypothesisCount
├── Polling: tags/live + anomalies every 5s (lifted to App level, persists across routes)
├── Header: dark mode toggle, Stats/Trace links, pipeline step nav (data-driven)
├── Routes:
│   / → Dashboard (live sensor grid, 3 agent cards, Cross-Sensor Corroboration card)
│   /anomalies → AnomalyDetection (9 checks grid, anomaly cards)
│   /hitl → HITLSelection (approve/reject)
│   /hypotheses → HypothesisView (root causes, confidence, actions)
│   /reports → ReportPreview (PDF/HTML/JSON download)
│   /trace → TraceView (Min/Full toggle, agent I/O log)
│   /stats → StatsForNerds (correlation matrix, causal groups, tech stack, FAQ)
└── api.js: VITE_API_BASE env variable (Render in prod, localhost in dev)
```

**State management:** useState + useEffect with 5-sec polling. Tags state lifted to App.jsx to persist across route changes (no flash on navigate back).

**Pipeline step progress:** Steps 0-4 highlight based on state:
- Step 0 (Profile): green when anomalyCount > 0
- Step 1 (Detect): green when anomalyCount > 0
- Step 2 (Review): green when all HITL decided
- Step 3 (Hypothesize): green when hypothesisCount > 0, accessible when approvedCount > 0 or all-rejected
- Step 4 (Report): accessible only when hypothesisCount > 0

**Dark mode:** `document.documentElement.classList.toggle('dark')` with localStorage persistence. CSS variables in index.css define both `:root` (light) and `.dark` (navy) palettes.

**All-rejected flow:** Steps 3-4 accessible even with no approvals. HypothesisView shows "All anomalies rejected — Continue to Report." Reports generate with empty anomalies (clean bill of health).

---

## Technology Choices — Why Each

| Tech | Why |
|---|---|
| **LangGraph** | Pipeline is a directed graph with a conditional edge (HITL). StateGraph makes this explicit and traceable. |
| **LangChain** | PromptTemplate, ChatOpenAI, JsonOutputParser — standard LLM interface. |
| **Groq Llama 3.1 8B Instant** | Fast inference (~2-5s per call), cost-efficient, good enough for pharma domain summaries. Replaces OpenAI GPT-4o. |
| **langchain_openai** v1.2+ | Uses `api_key` and `base_url` (not old `openai_api_key`/`openai_api_base`). Compatible with Groq. |
| **FastAPI** | Async REST API. Pydantic models for request/response validation. |
| **SQLAlchemy 2.0 async** | Async PostgreSQL with `asyncpg` driver for concurrent DB queries in agents. |
| **PostgreSQL JSONB** | `evidence` column stores nested JSON (witness details, correlation values, is_silent_lie). |
| **NumPy/SciPy** | Rolling means, z-scores, Pearson r — all statistical checks are pure numpy/scipy. |
| **React + Vite + Tailwind** | Component UI, fast HMR, utility-first CSS with dark mode. |
| **asyncpg** | Direct async SQL for bulk queries (1 query instead of N+1 per-tag). |

---

## Design Decisions

### 1. "Deterministic-first, AI-second" Agent Pattern
Rules always run (9 checks on every tag). LLM adds interpretation on top. This gives 100% check coverage and auditability. A "true agent" with tool calling would be more flexible but less predictable — the LLM might forget to run an important check.

### 2. Merged Agent 1 into Agent 2
Agent 1 (Data Profiler) was a separate pass that loaded all data, computed stats, then called LLM to interpret. Now Agent 2 computes profiles inline from the same data_cache — no separate DB round-trip, no separate LLM call. This cut detection time from ~30s to ~5-8s.

### 3. Async LLM Prioritization
Agent 2's LLM call to prioritize anomalies was blocking the response. Now it runs in the background via `asyncio.ensure_future`. The detection returns immediately with a fallback summary ("N anomalies detected. Analyzing patterns..."), and the LLM text updates later. This is non-critical — the deterministic priority sort (by type + confidence) is already correct.

### 4. Single Bulk Query
Instead of `SELECT * FROM tag_readings WHERE tag_id = ?` in a loop (N+1 queries), Agent 2 uses `_load_all_readings()` — one query that fetches all readings, then groups them in Python. Same approach for the profiler (now merged). This eliminated ~85 redundant DB queries.

### 5. Adaptive Window Sizes
All checks compute window sizes from `86400/n` (seconds per sample). This makes them work on any interval — 5s, 30s, 1min — without hardcoded window sizes.

### 6. Random 2-4 Anomalies Per Reseed
Each reseed picks 2-4 random anomalies from a pool of 6 templates, with no tag overlap. This makes the demo more interesting — you get different faults each time. Priority sort ensures cross_sensor_inconsistency > sensor_drift > stuck_value > others.

### 7. HITL Before Agent 3, Not After
Review before AI generates root causes. Cheaper (no wasted LLM calls on false alarms) and safer (AI doesn't act on unreviewed data).

### 8. Tags State Lifted to App.jsx
Tags were being fetched in Dashboard.jsx and re-fetched on every navigation, causing a flash. Now `liveTags` state lives in App.jsx and persists across routes — no flash on navigate back.

### 9. Guardrail on Output, Not Input
Pharma context means AI output is what reaches operators. Input-side filtering would miss legitimate data that happens to contain batch numbers. Output-side filtering catches PII that the LLM hallucinated.

### 10. Deterministic Silent Lie Injection
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