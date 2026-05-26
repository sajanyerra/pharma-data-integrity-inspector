# Mental Model: Pharma Data Integrity Inspector

## System Overview

This is a **multi-agent AI system** that monitors pharmaceutical sensor data for data integrity issues. Think of it as a "lie detector" for pharma manufacturing sensors.

## The Big Picture (4-Layer Architecture)

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 4: PRESENTATION (React Frontend)                     │
│  - Real-time dashboard (20 tags streaming)                  │
│  - HITL review interface (human approves AI findings)       │
│  - Report generation (PDF/HTML/JSON)                        │
│  - Agent trace viewer (transparency toggle)                 │
└─────────────────────────────────────────────────────────────┘
                            ↕ HTTP/REST
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3: AGENT ORCHESTRATION (FastAPI + LangChain)         │
│  - Agent 1: Data Profiler (statistics)                      │
│  - Agent 2: Anomaly Detector (10 checks)                    │
│  - Agent 3: Hypothesis Generator (root causes)              │
│  - Agent 4: Report Generator (outputs)                      │
└─────────────────────────────────────────────────────────────┘
                            ↕ SQLAlchemy (async)
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2: DATA PERSISTENCE (PostgreSQL)                     │
│  - tags: metadata for 20 sensors                            │
│  - tag_readings: time-series data (5-sec intervals)         │
│  - anomalies: detected issues + HITL status                 │
│  - agent_trace: full audit trail                            │
└─────────────────────────────────────────────────────────────┘
                            ↕ Python classes
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: DATA GENERATION (Tag Simulator)                   │
│  - 20 realistic pharma sensors                              │
│  - 2 pre-injected anomalies (drift + stuck value)           │
│  - Streams to database every 5 seconds                      │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow (Step-by-Step)

### 1. Data Generation (Continuous)
```
TagSimulator → generates 20 tag values → PostgreSQL (every 5 sec)
```
- Each tag has realistic baseline + noise
- 2 anomalies are pre-injected:
  - **TI-101**: Sensor drift (+2.5°C/hour starting at 14:32)
  - **VI-301**: Stuck value (frozen at 4.2 mm/s for 6 hours)

### 2. Analysis Pipeline (User-triggered)
```
User clicks "Run Analysis" → 
  Agent 1 (Data Profiler) → calculates statistics →
  Agent 2 (Anomaly Detector) → applies 10 checks →
  Saves anomalies to DB with status="pending" →
  User reviews in HITL view →
  User approves/rejects →
  Agent 3 (Hypothesis Generator) → root cause analysis →
  Agent 4 (Report Generator) → PDF/HTML/JSON
```

### 3. Agent Handoffs (LangChain)
```
Agent 1 Output = Agent 2 Input
Agent 2 Output → Database → HITL Selection → Agent 3 Input
Agent 3 Output → Database → Agent 4 Input
All handoffs logged to agent_trace table + LangSmith
```

## The 4 Agents (Detailed)

### Agent 1: Data Profiler
**Purpose**: Build baseline statistics for each tag

**Input**: 
- `hours`: How far back to analyze (default 24)
- `tag_ids`: Which tags to analyze (default all)

**Output**:
```json
{
  "tag_profiles": {
    "TI-101": {
      "count": 17280,
      "min": 172.3,
      "max": 178.9,
      "mean": 175.2,
      "std": 2.1,
      "median": 175.0,
      "q1": 173.5,
      "q3": 177.1,
      "quality_codes": {"Good": 17000, "Warning": 280},
      "update_frequency_per_hour": 720,
      "data_completeness": 98.5
    }
  }
}
```

**Algorithm**:
1. Query last N hours of readings
2. Calculate numpy statistics (min, max, mean, std, percentiles)
3. Count quality code distribution
4. Calculate update frequency (readings per hour)

---

### Agent 2: Anomaly Detector
**Purpose**: Apply 10 data integrity checks

**Input**: 
- `tag_profiles`: Output from Agent 1
- `hours`: Analysis window

**Output**:
```json
{
  "anomalies": [
    {
      "tag_id": "TI-101",
      "anomaly_type": "sensor_drift",
      "confidence": 0.85,
      "evidence": {
        "recent_mean": 178.5,
        "previous_mean": 175.2,
        "deviation_percent": 1.88,
        "drift_rate_per_hour": 0.31
      },
      "severity": "high"
    }
  ]
}
```

**10 Detection Algorithms**:

| # | Check | Algorithm | Threshold |
|---|-------|-----------|-----------|
| 1 | Sensor Drift | Rolling mean (1h vs 6h) | >1%/hour deviation |
| 2 | Stuck Value | Count unique values | <3 unique in 1h |
| 3 | Impossible Readings | Physical limits check | Outside range |
| 4 | Quality Code Mismatch | Good code but outliers | >5% outliers |
| 5 | Rate-of-Change | First derivative | dT/dt > threshold |
| 6 | Data Gaps | Timestamp continuity | Gap > 10 sec |
| 7 | Statistical Outliers | Z-score | |z| > 3 |
| 8 | Correlation Breakdown | Pearson correlation | r < 0.7 |
| 9 | CIP Anomaly | Temp/flow vs recipe | T < 70°C |
| 10 | FDA Audit Trail | Quality code patterns | >50% non-Good |

---

### Agent 3: Hypothesis Generator
**Purpose**: Generate root cause hypotheses for user-selected anomalies

**Input**:
- `anomalies`: List of approved anomalies from HITL step

**Output**:
```json
{
  "hypotheses": [
    {
      "tag_id": "TI-101",
      "anomaly_type": "sensor_drift",
      "root_cause": "Sensor calibration drift due to coating buildup on temperature probe",
      "confidence": 0.82,
      "recommended_action": "Schedule sensor calibration. Review calibration history.",
      "alternative_causes": [
        "Aging sensor element requiring replacement",
        "Temperature cycling causing sensor degradation"
      ],
      "pharma_impact": "May affect product quality if reactor temperature control is compromised"
    }
  ]
}
```

**LLM Prompt Structure**:
```
System: You are a pharma process engineer with 20 years experience...
Human: 
  Tag: {tag_id}, {tag_name}, {unit_type}
  Anomaly: {anomaly_type}
  Evidence: {evidence}
  Known causes: {knowledge_base}
  
Output JSON: {root_cause, confidence, recommended_action, alternatives, pharma_impact}
```

**Knowledge Base** (pre-defined root causes per anomaly type):
- `sensor_drift`: ["coating buildup", "aging sensor", "temperature cycling", ...]
- `stuck_value`: ["communication failure", "frozen transmitter", "network loss", ...]
- etc.

---

### Agent 4: Report Generator
**Purpose**: Create three output formats for different audiences

**Input**:
- `anomalies`: Detected anomalies
- `hypotheses`: Root cause analysis
- `tag_profiles`: Statistics

**Outputs**:
1. **PDF** (Executive Summary): 1-page overview with key metrics, top anomalies, compliance notes
2. **HTML** (Detailed Report): Interactive dashboard with full anomaly list, hypotheses, tag stats
3. **JSON** (Raw Data): Machine-readable export for engineers

**Technologies**:
- PDF: ReportLab (Python)
- HTML: Jinja2 templates + Tailwind CSS
- JSON: Python json module

---

## HITL Workflow (Human-in-the-Loop)

### Why HITL?
AI detects anomalies, but operators have context:
- "That sensor was just calibrated"
- "We had maintenance during that time"
- "This is expected behavior during batch changeover"

### Implementation
```
Agent 2 detects 5 anomalies → 
  UI shows list with Include/Reject buttons →
  User approves 3, rejects 2 →
  Agent 3 generates hypotheses for approved 3 only →
  Report includes only user-approved anomalies
```

### Database Schema
```sql
anomalies table:
  - id
  - tag_id
  - anomaly_type
  - confidence
  - evidence (JSONB)
  - hitl_status: 'pending' | 'approved' | 'rejected'
  - hypothesis (filled by Agent 3)
  - recommended_action (filled by Agent 3)
```

---

## LangSmith Integration (Trace Transparency)

### What Gets Traced?
Every agent handoff:
- Agent name
- Input data
- Output data
- Timestamp
- LLM prompts/responses (for Agents 3)

### Toggle View
**Minimal Mode**: Summary only (agent name, timestamp, result count)
**Full Mode**: Complete input/output JSON, expandable for each agent

### Why This Matters
- **FDA 21 CFR Part 11**: Electronic records require audit trails
- **Debugging**: See exactly what each agent did
- **Trust**: Operators can verify AI reasoning

---

## Frontend Architecture (React)

### Component Tree
```
App (root)
├── Sidebar (navigation)
├── TopBar (trace toggle, run analysis button)
└── Routes
    ├── Dashboard (real-time tag grid)
    ├── AnomalyDetection (list with filters)
    ├── HITLSelection (approve/reject interface)
    ├── HypothesisView (root cause cards)
    ├── ReportPreview (generate/download)
    └── TraceView (agent workflow log)
```

### State Management
- **Zustand**: Global UI state (sidebar open, trace mode)
- **TanStack Query**: Server state (anomalies, tags, traces)
- **React Router**: Navigation state

### Real-time Updates
```javascript
// Dashboard polls every 5 seconds
useEffect(() => {
  const fetchTags = async () => {
    const response = await axios.get('/tags/streaming')
    setTags(response.data)
  }
  fetchTags()
  const interval = setInterval(fetchTags, 5000)
  return () => clearInterval(interval)
}, [])
```

### Animations (Framer Motion)
- Streaming data: Fade transition on value updates
- Anomaly alerts: Pulse animation
- Page transitions: Slide/fade
- Agent progress: Staggered list animations

---

## Database Schema (PostgreSQL)

### tags
```sql
CREATE TABLE tags (
    tag_id VARCHAR(20) PRIMARY KEY,
    tag_name VARCHAR(100),
    unit_type VARCHAR(50),
    data_type VARCHAR(20),
    normal_min DECIMAL,
    normal_max DECIMAL,
    scan_rate_sec INT,
    description TEXT
);
```

### tag_readings (time-series)
```sql
CREATE TABLE tag_readings (
    id SERIAL PRIMARY KEY,
    tag_id VARCHAR(20) REFERENCES tags(tag_id),
    timestamp TIMESTAMPTZ NOT NULL,
    value DECIMAL,
    quality_code VARCHAR(10),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Critical index for fast time-range queries
CREATE INDEX idx_tag_readings_tag_timestamp 
ON tag_readings(tag_id, timestamp DESC);
```

### anomalies
```sql
CREATE TABLE anomalies (
    id SERIAL PRIMARY KEY,
    tag_id VARCHAR(20) REFERENCES tags(tag_id),
    anomaly_type VARCHAR(50),
    confidence DECIMAL,
    evidence JSONB,  -- Flexible schema for detection evidence
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    hitl_status VARCHAR(20) DEFAULT 'pending',
    hypothesis TEXT,
    recommended_action TEXT
);
```

### agent_trace (audit trail)
```sql
CREATE TABLE agent_trace (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(50),
    input JSONB,
    output JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Key Design Decisions

### 1. Pre-injected Anomalies (vs Random)
**Decision**: Use deterministic, pre-injected anomalies

**Why**:
- Reproducible demos (same anomalies every run)
- Known ground truth for validation
- Easier to explain in LinkedIn video

**Trade-off**: Less "realistic" but better for demos

### 2. HITL at Anomaly Selection (vs Per-Anomaly Approval)
**Decision**: User selects batch of anomalies to investigate

**Why**:
- Realistic workflow (operators prioritize)
- Not tedious (imagine approving 100 anomalies one-by-one)
- Demonstrates judgment (AI finds, human decides)

### 3. Three Report Formats (vs One)
**Decision**: PDF + HTML + JSON

**Why**:
- Different audiences need different views
- Executives: 1-page PDF summary
- Operations: Interactive HTML
- Engineers: Raw JSON for analysis

### 4. Trace Toggle (Minimal/Full)
**Decision**: Two modes for agent trace view

**Why**:
- Minimal: Clean, executive-friendly
- Full: Complete transparency for auditors
- Demonstrates "explainable AI" principle

### 5. On-Premise Ready Architecture
**Decision**: Swappable LLM provider

**Why**:
- Pharma requires air-gapped deployments
- Cannot rely on cloud APIs in production
- Demonstrates industrial awareness

**Implementation**:
```python
# config.py
OLLAMA_BASE_URL = os.getenv(
    'OLLAMA_BASE_URL',
    'https://ollama.cloud/v1'  # or 'http://localhost:11434/v1'
)
```

---

## Deployment Scenarios

### Development (Current)
```
PostgreSQL (D:\PostGre) → localhost:5432
Backend (FastAPI) → localhost:8000
Frontend (Vite) → localhost:5173
LLM → Ollama Cloud (API)
```

### Production (On-Premise)
```
PostgreSQL → On-prem server
Backend → Internal web server
Frontend → Nginx/Apache
LLM → Local Ollama (ollama pull qwen3.5:397b)
LangSmith → Optional (can disable for air-gap)
```

### Air-Gapped (No Internet)
```
All components local:
- PostgreSQL on-prem
- Ollama local (pre-downloaded models)
- LangSmith tracing disabled
- Frontend served from internal server
```

---

## Testing the System

### 1. Check Backend Health
```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy","timestamp":"..."}
```

### 2. Check Tag Streaming
```bash
curl http://localhost:8000/tags/streaming
# Expected: 20 tags with values updating every 5 sec
```

### 3. Run Analysis
```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"hours": 24}'
# Expected: {"anomalies_detected": {...}}
```

### 4. Check Anomalies
```bash
curl http://localhost:8000/anomalies
# Expected: List of detected anomalies
```

### 5. Generate Hypotheses
```bash
curl -X POST http://localhost:8000/generate-hypotheses
# Expected: {"hypotheses": [...]}
```

### 6. Generate Reports
```bash
curl -X POST http://localhost:8000/generate-reports
# Expected: {"reports": {"pdf": "...", "html": "...", "json": "..."}}
```

---

## Common Issues & Solutions

### Issue: Backend won't start
**Symptom**: `ModuleNotFoundError: No module named 'psycopg2'`
**Solution**: `uv pip install psycopg2-binary`

### Issue: Database connection failed
**Symptom**: `password authentication failed for user "postgres"`
**Solution**: Check DATABASE_URL in .env (use pharma_user:pharma_pass)

### Issue: Frontend can't connect to backend
**Symptom**: CORS errors in browser console
**Solution**: Ensure backend CORS middleware allows localhost:5173

### Issue: LLM not responding
**Symptom**: Timeout in hypothesis generation
**Solution**: Check OLLAMA_CLOUD_API_KEY in .env, or switch to local Ollama

### Issue: Anomalies not detected
**Symptom**: Empty anomalies list after analysis
**Solution**: Ensure tag_readings table has data (run stream_ingest.py)

---

## Mental Model Summary

Think of this system as a **quality control inspector** for pharma sensor data:

1. **Eyes** (Dashboard): Watches 20 sensors in real-time
2. **Brain** (Agents 1-2): Analyzes patterns, detects anomalies
3. **Judgment** (HITL): Human validates AI findings
4. **Reasoning** (Agent 3): Explains why anomalies occurred
5. **Communication** (Agent 4): Reports to stakeholders
6. **Memory** (Database): Stores everything for audits
7. **Transparency** (LangSmith): Shows all reasoning steps

The key innovation is **Human-in-the-Loop**: AI doesn't make final decisions, it presents candidates for human review. This builds trust and reduces false positive waste.

---

## Next Steps (After Building)

1. **Run Stream Ingest**: Start data streaming
   ```bash
   cd backend
   .\.venv\Scripts\python.exe stream_ingest.py
   ```

2. **Run Analysis**: Click "Run Analysis" in UI

3. **Review HITL**: Go to HITL view, approve anomalies

4. **Generate Hypotheses**: Auto-triggers after approval

5. **Generate Reports**: Download PDF/HTML/JSON

6. **View Trace**: Toggle to Full mode, see agent workflow

7. **Record Demo**: Follow LinkedIn video script

---

**Built with ❤️ for pharma data integrity**
