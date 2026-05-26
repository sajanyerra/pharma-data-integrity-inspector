# Quick Start Guide

## Current Status ✅

- ✅ PostgreSQL 18 running (D:\PostGre)
- ✅ Database `pharma_data` created
- ✅ 20 pharma tags seeded
- ✅ Backend running on http://localhost:8000
- ✅ Frontend running on http://localhost:5173

## Access the Application

**Open your browser**: http://localhost:5173

You should see the Dashboard with 20 streaming tags!

## Start Data Streaming (Optional)

To continuously stream data to the database:

```bash
cd D:\Projects\AVP\pharma-data-integrity-inspector\backend
.\.venv\Scripts\python.exe stream_ingest.py
```

This will insert new readings every 5 seconds.

**Note**: The simulation includes 2 pre-injected anomalies:
- **TI-101** (Reactor Temp): Sensor drift starting at 14:32 (+2.5°C/hour)
- **VI-301** (Pump Vibration): Stuck value at 03:15 (frozen for 6 hours)

## Run Full Analysis

1. **Open Dashboard** (http://localhost:5173)
2. Click **"Run Analysis"** button (top right)
3. Wait for analysis to complete (~10-30 seconds)
4. Navigate to **Anomaly Detection** view
5. Review detected anomalies

## HITL Review Workflow

1. Go to **HITL Review** (sidebar)
2. Review each anomaly
3. Click **✓** (green) to approve for investigation
4. Click **✗** (red) to reject as false positive
5. Add optional comments
6. Click **"Submit Selections"**

## Generate Hypotheses

After approving anomalies in HITL:

1. Go to **Hypotheses** view
2. AI generates root cause analysis automatically
3. Review hypotheses with confidence scores
4. See recommended actions

## Generate Reports

1. Go to **Reports** view
2. Click **"Generate Reports"**
3. Download:
   - **PDF**: Executive summary
   - **HTML**: Detailed technical report
   - **JSON**: Raw data export

## View Agent Trace

1. Go to **Agent Trace** view
2. Toggle between **Minimal** and **Full** trace modes
3. Click to expand individual agent runs
4. See complete input/output for each agent

## Restart Servers (If Needed)

### Backend
```bash
cd D:\Projects\AVP\pharma-data-integrity-inspector\backend
.\.venv\Scripts\uvicorn.exe main:app --reload
```

### Frontend
```bash
cd D:\Projects\AVP\pharma-data-integrity-inspector\frontend
npm run dev
```

## Environment Variables

Edit `backend\.env` to configure:

```env
# Database (already configured)
DATABASE_URL=postgresql://pharma_user:pharma_pass@localhost:5432/pharma_data

# LangSmith (optional - for trace tracking)
LANGSMITH_API_KEY=your-api-key-here

# LLM (Ollama Cloud or local)
OLLAMA_CLOUD_API_KEY=your-api-key-here
OLLAMA_BASE_URL=https://ollama.cloud/v1
OLLAMA_MODEL=qwen3.5:397b
```

## Project Structure

```
pharma-data-integrity-inspector/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── database.py          # SQLAlchemy setup
│   ├── models.py            # Database models
│   ├── config.py            # Configuration
│   ├── tag_simulator.py     # Sensor data simulator
│   ├── stream_ingest.py     # Data streaming service
│   ├── agents/
│   │   ├── base.py          # Base agent class
│   │   ├── data_profiler.py # Agent 1
│   │   ├── anomaly_detector.py  # Agent 2
│   │   ├── hypothesis_generator.py  # Agent 3
│   │   └── report_generator.py  # Agent 4
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Main app component
│   │   ├── main.jsx         # Entry point
│   │   └── pages/           # Page components
│   └── package.json
├── scripts/
│   ├── create_schema.sql    # Database schema
│   └── seed_tags.sql        # Tag metadata
├── reports/                  # Generated reports
├── README.md
└── MENTAL_MODEL.md          # Detailed mental model
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/tags` | GET | All tag metadata |
| `/tags/streaming` | GET | Latest readings |
| `/anomalies` | GET | Detected anomalies |
| `/analyze` | POST | Run multi-agent analysis |
| `/generate-hypotheses` | POST | Generate root causes |
| `/generate-reports` | POST | Create reports |
| `/trace` | GET | Agent execution log |

## Troubleshooting

### Backend won't start
```bash
cd backend
uv pip install -r requirements.txt  # Reinstall dependencies
```

### Frontend shows blank page
```bash
cd frontend
npm install  # Reinstall packages
npm run dev  # Restart dev server
```

### Database connection error
Check PostgreSQL is running:
```bash
Get-Service -Name "postgresql-x64-18"
```

### Port 8000 already in use
Kill existing process:
```bash
Get-NetTCPConnection -LocalPort 8000 | Stop-NetTCPConnection -Confirm:$false
```

## Demo Checklist

For LinkedIn demo video:

- [ ] Dashboard shows 20 streaming tags
- [ ] Click "Run Analysis" button
- [ ] Show Anomaly Detection view with detected issues
- [ ] Show HITL Review (approve/reject anomalies)
- [ ] Show Hypotheses view (root cause analysis)
- [ ] Show Reports view (generate PDF/HTML/JSON)
- [ ] Toggle Agent Trace (Minimal → Full view)
- [ ] Mention: "Built with LangChain multi-agents, PostgreSQL, React"
- [ ] Mention: "Supports on-premise deployment for air-gapped environments"

---

**Ready to go! Open http://localhost:5173 in your browser.**
