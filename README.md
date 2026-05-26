# Pharma Data Integrity Inspector

AI multi-agent system for detecting data integrity issues in pharmaceutical manufacturing sensor data.

## Problem

Pharmaceutical manufacturing relies on trusted sensor data for quality control and regulatory compliance. However, PI historian systems accumulate data integrity issues:

- **Sensor drift** (undetected for hours/days)
- **Stuck values** (frozen tags)
- **Impossible readings** (negative pressure, temperatures beyond physical limits)
- **Correlation breakdowns** (related tags diverge)
- **Quality code mismatches** (tag marked 'good' but data looks wrong)
- **FDA 21 CFR Part 11** audit trail gaps

Operators lose trust in data. Engineers spend days manually auditing trends. Compliance teams struggle to prove data integrity during inspections.

## Solution

A multi-agent AI system that:

✅ Monitors 20 process tags streaming at 5-second intervals  
✅ Applies 10 data integrity checks automatically  
✅ Human-in-the-loop anomaly selection (AI flags, human decides)  
✅ Generates root cause hypotheses with pharma context  
✅ Produces PDF + HTML + JSON reports  
✅ Full agent workflow transparency via toggle (Minimal/Full trace)  
✅ Supports on-premise deployment (local LLM, air-gap ready architecture)

## Demo

**2-minute video walkthrough**: [Link to video]

**Sample Reports**:
- [Executive Summary PDF](reports/sample_executive.pdf)
- [Detailed HTML Report](reports/sample_detailed.html)
- [Raw Data JSON](reports/sample_data.json)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 PHARMA DATA INTEGRITY INSPECTOR              │
├─────────────────────────────────────────────────────────────┤
│  Tag Simulator (20 tags) → Stream Ingest → PostgreSQL       │
│                                          ↓                   │
│  Agent 1: Data Profiler → Agent 2: Anomaly Detector         │
│                                          ↓                   │
│  HITL: User Selection → Agent 3: Hypothesis Generator       │
│                                          ↓                   │
│  Agent 4: Report Generator → PDF/HTML/JSON Export           │
│                                          ↓                   │
│  LangSmith Trace (Toggle: Minimal/Full)                     │
└─────────────────────────────────────────────────────────────┘
```

## Tech Stack

**Frontend**:
- React 18 + Vite
- Tailwind CSS v3
- Framer Motion (animations)
- React Router DOM
- Zustand (state management)
- TanStack Query (data fetching)

**Backend**:
- FastAPI (Python)
- SQLAlchemy + asyncpg
- LangChain (multi-agent orchestration)
- LangSmith (trace tracking)
- Ollama Cloud (LLM: qwen3.5:397b)
- ReportLab (PDF generation)
- Jinja2 (HTML templates)

**Database**:
- PostgreSQL 18 (time-series data)

## Quick Start

### Prerequisites

- Python 3.10+ with uv
- Node.js 18+ and npm
- PostgreSQL 18+

### 1. Clone Repository

```bash
cd D:\Projects\AVP\pharma-data-integrity-inspector
```

### 2. Setup Database

```bash
# PostgreSQL is already running with pharma_data database
# Tags are seeded (20 pharma process tags)
```

### 3. Install Backend Dependencies

```bash
cd backend
uv venv
uv pip install -r requirements.txt
```

### 4. Configure Environment

```bash
# Edit backend/.env with your API keys
# - LangSmith API key (optional for tracing)
# - Ollama Cloud API key (or use local Ollama)
```

### 5. Start Backend

```bash
cd backend
uv run python main.py
# Runs on http://localhost:8000
```

### 6. Start Frontend

```bash
cd frontend
npm run dev
# Runs on http://localhost:5173
```

### 7. Open Browser

```
http://localhost:5173
```

## Anomaly Detection Algorithms (10 Checks)

### Universal Checks (7)
1. **Sensor Drift** - Rolling mean comparison (1h vs 6h window)
2. **Stuck Value (Flatline)** - <3 unique values in 1 hour
3. **Impossible Readings** - Outside physical limits
4. **Correlation Breakdown** - Pearson r < 0.7 for related tags
5. **Quality Code Mismatch** - 'Good' code but statistical outliers
6. **Rate-of-Change Violation** - dT/dt > threshold
7. **Data Gaps** - Gap > 2x scan rate (10 sec)

### Pharma-Specific Checks (3)
8. **FDA 21 CFR Part 11 Audit Trail** - Unlogged changes
9. **Batch Consistency** - >5% deviation from historical batches
10. **CIP Cycle Anomaly** - T < 70°C or flow < 500 L/min during CIP

## Multi-Agent Architecture

### Agent 1: Data Profiler
Analyzes 24h of tag data, builds baseline statistics (min, max, mean, std, update frequency)

### Agent 2: Anomaly Detector
Applies 10 detection algorithms, flags suspicious tags with confidence scores

### Agent 3: Hypothesis Generator
Generates root cause hypotheses for user-selected anomalies with pharma context

### Agent 4: Report Generator
Creates three output formats:
- **PDF**: Executive summary (1-page overview)
- **HTML**: Detailed technical report
- **JSON**: Raw data export for engineers

## Injected Demo Anomalies

This simulation includes 2 pre-injected anomalies for reproducible demos:

| Tag | Type | Start Time | Duration | Description |
|-----|------|------------|----------|-------------|
| TI-101 | Sensor Drift | 14:32:00 | 18 hours | +2.5°C/hour drift |
| VI-301 | Stuck Value | 03:15:00 | 6 hours | Frozen at 4.2 mm/s |

## On-Premise Deployment

This system is designed for air-gapped industrial environments:

1. **Local LLM**: Replace Ollama Cloud with local Ollama instance
   ```bash
   ollama pull qwen3.5:397b
   # Update OLLAMA_BASE_URL to http://localhost:11434/v1
   ```

2. **Local Database**: PostgreSQL runs on-premise (no cloud dependency)

3. **Local Frontend**: Serve React app from internal web server

4. **No External API Calls**: All processing happens locally

5. **Compliance**: Architecture supports FDA 21 CFR Part 11 requirements

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/tags` | Get all tag metadata |
| GET | `/tags/{id}/readings` | Get tag readings |
| GET | `/tags/streaming` | Get latest readings (dashboard) |
| GET | `/anomalies` | Get detected anomalies |
| POST | `/anomalies/select` | Update HITL status |
| POST | `/analyze` | Run multi-agent analysis |
| POST | `/generate-hypotheses` | Generate root causes |
| POST | `/generate-reports` | Create PDF/HTML/JSON |
| GET | `/trace` | Get agent execution trace |

## LinkedIn Strategy

### Demo Video Script (2-3 minutes)

| Time | Visual | Narration |
|------|--------|-----------|
| 0:00-0:15 | Dashboard home, 20 tags streaming | "Pharma manufacturing relies on trusted sensor data. But what if your sensors are lying to you?" |
| 0:15-0:30 | Zoom on TI-101 (reactor temp) | "This reactor temperature sensor has been drifting for 18 hours. Nobody noticed." |
| 0:30-0:45 | Anomaly detection view | "I built an AI multi-agent system that finds data integrity issues automatically. It found 5 problems in 24 hours." |
| 0:45-1:00 | HITL view, user selecting | "Here's the key: human in the loop. The AI flags candidates, but the operator decides what to investigate." |
| 1:00-1:20 | Hypothesis view | "For each selected anomaly, AI generates root cause hypotheses. 'Sensor drift due to coating buildup - recommend calibration.'" |
| 1:20-1:40 | Report preview | "Three output formats: PDF for executives, HTML for operations, JSON for engineers." |
| 1:40-2:00 | Trace toggle: Minimal → Full | "Full transparency: toggle between summary view and full agent workflow." |
| 2:00-2:15 | LangSmith trace screenshot | "LangSmith integration tracks every agent handoff. This is production-grade AI engineering." |
| 2:15-2:30 | Back to dashboard | "Built with React, PostgreSQL, LangChain multi-agents, and Ollama. Supports on-premise deployment." |
| 2:30-2:45 | GitHub URL | "Code is on GitHub. If you're hiring for AI + industrial roles, let's talk." |

### Screenshot Checklist

- [ ] Dashboard Home - 20 tags streaming
- [ ] Anomaly Detection View - List of flagged issues
- [ ] HITL Selection View - User approving/rejecting
- [ ] Hypothesis View - Root cause analysis
- [ ] Report Preview - PDF/HTML/JSON tabs
- [ ] Trace Toggle (Minimal) - Clean summary
- [ ] Trace Toggle (Full) - All agent inputs/outputs
- [ ] LangSmith Trace - External screenshot
- [ ] Mobile View - Dashboard on iPhone frame
- [ ] Architecture Diagram - System overview

## License

MIT

---

**Built with ❤️ for pharma data integrity**
