# Pharma Data Integrity Inspector

**3 AI agents that catch sensor data your historian misses — including sensors that are wrong but look perfectly normal.**

Most pharma data quality tools check each sensor in isolation: thresholds, quality codes, range checks. They all miss the same thing — a sensor reading 172°C when the real temperature is 175°C. It passes every check. Quality code says "Good." No alarm fires. But the batch is compromised.

Cross-Sensor Corroboration fixes this by cross-referencing physically-coupled sensors. When a temperature sensor says one thing but the correlated pressure and flow sensors say another, we catch it — even though no individual threshold was breached.

---

## Screenshots

| Dashboard | Anomaly Detection | Cross-Sensor Corroboration |
|---|---|---|
| *[Dashboard]* | *[Anomalies]* | *[Corroboration]* |

---

## What It Does

- **3 AI agents** orchestrated by LangGraph: Anomaly Detector (with inline profiling) → (HITL gate) → Hypothesis Generator → Report Generator
- **9 integrity checks** — 8 standard + Check 9: Cross-Sensor Corroboration (novel)
- **Human-in-the-Loop gate** between Agent 2 and Agent 3 — you approve anomalies before AI generates root causes (FDA 21 CFR Part 11 aligned)
- **Output Guardrail** — PII, batch numbers, credentials, and dangerous recommendations are blocked before any AI output reaches the user
- **Random anomalies each run** — 2-4 from a pool of 6 types (drift, stuck, spike, noise_burst, silent_lie), no tag overlap
- **Fast detection** — ~5-8s instead of ~30s thanks to merged profiler, single SQL query, and async LLM calls
- **Dark mode** with navy palette, guided pipeline steps as navigation, "Next Step" CTAs
- **Stats for Nerds** page for curious learners

## The Novel Check: Cross-Sensor Corroboration (Check 9)

Most data quality tools operate per-sensor. If a reading is within range and has a "Good" quality code, it passes. Check 9 does something different: it segments the correlation timeline between a suspect tag and its physically-coupled witness sensors. When the correlation pattern changes and the trend direction contradicts what physics predicts, the sensor is flagged — even though no individual threshold was breached.

**Example:** TI-101 reports 172°C (normal range, Good quality). But PI-101 trends upward (suggesting 175°C+) and FI-201 rises (cooling compensating for heat you can't see). The sensor is wrong by 3°C. No historian catches that. We do.

---

## Architecture

```
TagSimulator (20 tags, 30s interval, causal couplings + random 2-4 anomalies)
    ↓
Agent 2: Anomaly Detector ─── 1 bulk query + inline profiles + 9 checks + Llama 3.1 (async) ─── flags issues
    ↓
HITL Gate ─── human approves/rejects ─── FDA 21 CFR Part 11
    ↓
Agent 3: Hypothesis Generator ─── Llama 3.1 + domain KB ─── root causes + remediation
    ↓
Agent 4: Report Generator ─── Llama 3.1 + Jinja2 ─── PDF/HTML/JSON
    ↓
OutputGuardrail ─── PII, pharma-sensitive, dangerous recs ─── blocks before user sees
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Groq Llama 3.1 8B Instant (via langchain_openai) |
| Orchestration | LangGraph StateGraph, LangChain |
| Backend | FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| Data/Stats | NumPy, SciPy (Pearson r, p-values) |
| Database | PostgreSQL (Render) |
| Safety | OutputGuardrail (regex + pattern matching + confidence bounding) |
| Reporting | ReportLab (PDF), Jinja2 (HTML) |
| Frontend | React 19, Vite, Tailwind CSS (dark mode), Framer Motion |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 16+

### 1. Clone & Setup

```bash
git clone https://github.com/sajanyerra/pharma-data-integrity-inspector.git
cd pharma-data-integrity-inspector
```

### 2. Database

```bash
# Create PostgreSQL database
createdb pharma_data

# Create schema
psql -d pharma_data -f scripts/create_schema.sql

# Seed tag metadata
psql -d pharma_data -f scripts/seed_tags.sql
```

### 3. Backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

# Copy and edit .env with your keys
cp .env.example .env
# Set LLM_API_KEY (Groq key, required)
# Set LLM_BASE_URL=https://api.groq.com/openai/v1
# Set LLM_MODEL=llama-3.1-8b-instant
# Set DATABASE_URL (PostgreSQL connection string)

# Seed 24h of historical data
python seed_historical_data.py

# Start server
python main.py
# Runs on http://localhost:8000
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:5173
```

Open http://localhost:5173 and click **Start Analysis**.

---

## 9 Active Integrity Checks

| # | Check | What It Catches | Method |
|---|---|---|---|
| 1 | Sensor Drift | Gradual calibration degradation | Rolling mean comparison (1h vs 6h, threshold 1%/hr) |
| 2 | Stuck Value | Transmitter stopped updating | Adaptive window, <3 unique values |
| 3 | Impossible Readings | Outside physical possibility | Per-datatype limits (e.g., T < -273°C) |
| 4 | Rate-of-Change | Impossible step changes | Type-specific thresholds, >10 violations |
| 5 | Noise Burst | Sudden noise spikes | >5x baseline std deviation |
| 6 | Correlation Breakdown | Related tags stopped correlating | Split-half Pearson r shift > 0.8 |
| 7 | CIP Temperature Low | Incomplete cleaning cycle | CIP supply temp < 70°C |
| 8 | FDA Audit Trail | 21 CFR Part 11 concern | >50% non-Good quality codes |
| **9** | **Cross-Sensor Corroboration** | **Sensor PLAUSIBLE but WRONG** | **Segmented correlation + trend direction with witness sensors** |

---

## Random Anomaly Pool

The TagSimulator injects 2-4 random anomalies per reseed from this pool (no tag overlap):

| Type | Example Tags | What Happens |
|------|-------------|-------------|
| `sensor_drift` | TI-101, PI-101 | Gradual drift at 1-5%/hr |
| `stuck_value` | VI-301, PI-401 | Value frozen for 2-8 hours |
| `spike` | TI-101, AI-901 | Sudden 3-8x multiplier |
| `noise_burst` | TI-201, VI-301 | 3-8x noise for 1-4 hours |
| `silent_lie` | TI-101, TI-201 | 2-6% offset with Good quality code |
| `sensor_drift` (slow) | PI-502, FI-601 | Slow drift at 0.5-2% (harder to detect) |

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | System status |
| GET | `/tags/live` | Live tag values (30s refresh) |
| GET | `/anomalies` | Detected anomalies |
| POST | `/analyze` | Run Anomaly Detector pipeline |
| POST | `/anomalies/select-batch` | HITL approve/reject |
| POST | `/generate-hypotheses` | Agent 3 root causes |
| POST | `/generate-reports` | Agent 4 reports |
| GET | `/reports/download/{type}` | Download PDF/HTML/JSON |
| GET | `/trace` | Agent execution log |
| GET | `/stats/correlations` | Live correlation matrix |
| GET | `/stats/causal-groups` | Causal model definition |
| GET | `/stats/integrity-checks` | All 9 check metadata |
| GET | `/stats/tech-stack` | Technology stack details |
| GET | `/stats/pipeline` | Pipeline architecture info |
| POST | `/reseed` | Reseed data with new random anomalies |
| POST | `/reset` | Clear anomalies and traces |

---

## Deployment

### Render (Backend + PostgreSQL)

1. Create a new **Web Service** on Render, connect your GitHub repo
2. Set root directory to `backend/`
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add PostgreSQL addon on Render
6. Set environment variables: `LLM_API_KEY` (Groq), `LLM_BASE_URL`, `LLM_MODEL`, `DATABASE_URL`

### Vercel (Frontend)

1. Create new project on Vercel, connect GitHub repo
2. Set root directory to `frontend/`
3. Framework: Vite
4. Set `VITE_API_BASE` environment variable to your Render backend URL

---

## License

MIT