# Pharma Data Integrity Inspector

**4 AI agents that catch sensor data your historian misses — including sensors that are wrong but look perfectly normal.**

Most pharma data quality tools check each sensor in isolation: thresholds, quality codes, range checks. They all miss the same thing — a sensor reading 172°C when the real temperature is 175°C. It passes every check. Quality code says "Good." No alarm fires. But the batch is compromised.

Cross-Sensor Corroboration fixes this by cross-referencing physically-coupled sensors. When a temperature sensor says one thing but the correlated pressure and flow sensors say another, we catch it — even though no individual threshold was breached.

---

## Screenshots

| Dashboard | Anomaly Detection | Cross-Sensor Corroboration |
|---|---|---|
| *[Dashboard]* | *[Anomalies]* | *[Corroboration]* |

---

## What It Does

- **4 AI agents** orchestrated by LangGraph: Data Profiler → Anomaly Detector → (HITL gate) → Hypothesis Generator → Report Generator
- **11 integrity checks** — 10 standard + Check 11: Cross-Sensor Corroboration (novel)
- **Human-in-the-Loop gate** between Agent 2 and Agent 3 — you approve anomalies before AI generates root causes (FDA 21 CFR Part 11 aligned)
- **Output Guardrail** — PII, batch numbers, credentials, and dangerous recommendations are blocked before any AI output reaches the user
- **Causal tag simulator** with physics-based coupling (Clausius-Clapeyron, mass balance, pump curves) — not random noise
- **Dark mode** with navy palette, data-driven navigation, Stats for Nerds page

## The Novel Check: Cross-Sensor Corroboration (Check 11)

Most data quality tools operate per-sensor. If a reading is within range and has a "Good" quality code, it passes. Check 11 does something different: it segments the correlation timeline between a suspect tag and its physically-coupled witness sensors. When the correlation pattern changes and the trend direction contradicts what physics predicts, the sensor is flagged — even though no individual threshold was breached.

**Example:** TI-101 reports 172°C (normal range, Good quality). But PI-101 trends upward (suggesting 175°C+) and FI-201 rises (cooling compensating for heat you can't see). The sensor is wrong by 3°C. No historian catches that. We do.

---

## Architecture

```
TagSimulator (20 tags, 5s interval, causal couplings + Silent Lie injection)
    ↓
Agent 1: Data Profiler ─── SQL + numpy + GPT-4o ─── builds baselines
    ↓
Agent 2: Anomaly Detector ─── 11 checks + GPT-4o ─── flags issues, AI analyzes patterns
    ↓
HITL Gate ─── human approves/rejects ─── FDA 21 CFR Part 11
    ↓
Agent 3: Hypothesis Generator ─── GPT-4o + domain KB ─── root causes + remediation
    ↓
Agent 4: Report Generator ─── GPT-4o + Jinja2 ─── PDF/HTML/JSON
    ↓
OutputGuardrail ─── PII, pharma-sensitive, dangerous recs ─── blocks before user sees
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | OpenAI GPT-4o |
| Orchestration | LangGraph StateGraph, LangChain, LangSmith (EU) |
| Backend | FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| Data/Stats | NumPy, SciPy (Pearson r, p-values), Pandas |
| Database | PostgreSQL 18 |
| Safety | OutputGuardrail (regex + pattern matching + confidence bounding) |
| Reporting | ReportLab (PDF), Jinja2 (HTML) |
| Frontend | React 19, Vite, Tailwind CSS (dark mode), Framer Motion |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 18+

### 1. Clone & Setup

```bash
git clone https://github.com/YOUR_USERNAME/pharma-data-integrity-inspector.git
cd pharma-data-integrity-inspector
```

### 2. Database

```bash
# Create PostgreSQL database
psql -U postgres -c "CREATE USER pharma_user WITH PASSWORD 'pharma_pass';"
psql -U postgres -c "CREATE DATABASE pharma_data OWNER pharma_user;"

# Create schema
psql -U pharma_user -d pharma_data -f scripts/create_schema.sql

# Seed tag metadata
psql -U pharma_user -d pharma_data -f scripts/seed_tags.sql
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
# Set OPENAI_API_KEY (required)
# Set LANGSMITH_API_KEY (optional, for tracing)

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

### 5. Or use the start script

```bash
# Windows — starts both servers
start-servers.bat
```

Open http://localhost:5173 and click **Start Analysis**.

---

## 11 Integrity Checks

| # | Check | What It Catches | Method |
|---|---|---|---|
| 1 | Sensor Drift | Gradual calibration degradation | Rolling mean comparison (1h vs 6h) |
| 2 | Stuck Value | Transmitter stopped updating | <3 unique values in sliding window |
| 3 | Impossible Readings | Outside physical possibility | Per-datatype limits (e.g., T < -273°C) |
| 4 | Quality Code Mismatch | SCADA says Good but data is outlier | IQR outlier % vs Good quality % |
| 5 | Rate-of-Change | Impossible step changes | Delta between consecutive 5-sec readings |
| 6 | Data Gaps | Missing historian data | Time gap > 2× scan rate |
| 7 | Statistical Outliers | Extreme value deviations | Z-score > 5, >5% of readings |
| 8 | Correlation Breakdown | Related tags stopped correlating | Split-half Pearson r shift > 0.6 |
| 9 | CIP Temperature Low | Incomplete cleaning cycle | CIP supply temp < 70°C |
| 10 | FDA Audit Trail | 21 CFR Part 11 concern | >50% non-Good quality codes |
| **11** | **Cross-Sensor Corroboration** | **Sensor PLAUSIBLE but WRONG** | **Segmented correlation + trend direction** |

---

## Demo Anomalies

The TagSimulator injects 3 reproducible anomalies:

| Tag | Type | Description |
|---|---|---|
| TI-101 | Sensor Drift | +2.5°C/hr drift starting at hour 10 |
| VI-301 | Stuck Value | Frozen at 4.2 mm/s for 6 hours |
| TI-101 | Cross-Sensor Inconsistency | 3°C offset (172 vs 175°C) hours 10-14, Good quality code |

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | System status |
| GET | `/tags/live` | Live tag values (5s refresh) |
| GET | `/anomalies` | Detected anomalies |
| POST | `/analyze` | Run Agent 1-2 pipeline |
| POST | `/anomalies/select` | HITL approve/reject |
| POST | `/generate-hypotheses` | Agent 3 root causes |
| POST | `/generate-reports` | Agent 4 reports |
| GET | `/trace` | Agent execution log |
| GET | `/stats/correlations` | Live correlation matrix |
| GET | `/stats/causal-groups` | Causal model definition |
| GET | `/stats/integrity-checks` | All 11 check metadata |
| GET | `/stats/tech-stack` | Technology stack details |
| GET | `/stats/pipeline` | Pipeline architecture info |

---

## Deployment

### Render (Backend + PostgreSQL)

1. Create a new **Web Service** on Render, connect your GitHub repo
2. Set root directory to `backend/`
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add PostgreSQL addon on Render
6. Set environment variables: `OPENAI_API_KEY`, `DATABASE_URL`, `LANGSMITH_API_KEY` (optional)

### Vercel (Frontend)

1. Create new project on Vercel, connect GitHub repo
2. Set root directory to `frontend/`
3. Framework: Vite
4. Set `VITE_API_BASE` environment variable to your Render backend URL
5. Update `API_BASE` in each page component to use `import.meta.env.VITE_API_BASE`

---

## License

MIT