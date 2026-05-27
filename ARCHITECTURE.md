# Pharma Data Integrity Inspector — Architecture

## System Overview

```mermaid
graph TB
    subgraph Frontend ["React + Vite + Tailwind"]
        Dashboard["Dashboard<br/>Live tag values (lifted state)"]
        AnomalyPage["Anomaly Detection<br/>9 checks + results"]
        HITL["HITL Review<br/>Approve / Reject"]
        HypoPage["Hypothesis View<br/>Root causes"]
        ReportPage["Report Preview<br/>PDF / HTML / JSON"]
        TracePage["Trace View<br/>Agent I/O logs"]
        StatsPage["Stats for Nerds<br/>Correlations + tech stack"]
    end

    subgraph Backend ["FastAPI Backend"]
        API["REST API<br/>/analyze, /anomalies, /tags, etc."]
        Pipeline["LangGraph StateGraph<br/>3-Agent Pipeline"]
        Agents["Agent Layer"]
        Guardrail["OutputGuardrail<br/>PII / pharma / credentials"]
        Simulator["TagSimulator<br/>20 tags, causal couplings, random 2-4 anomalies"]
    end

    subgraph Database ["PostgreSQL"]
        Tags["tags<br/>20 pharma sensor configs"]
        Readings["tag_readings<br/>24h @ 30s intervals ~2,880/tag"]
        AnomaliesTable["anomalies<br/>JSONB evidence, HITL status"]
        Traces["agent_trace<br/>LLM input/output logs"]
    end

    subgraph LLM ["Groq Llama 3.1 8B Instant"]
        LLM2["Agent 2: Anomaly Detector<br/>(async prioritization)"]
        LLM3["Agent 3: Hypothesis Generator"]
        LLM4["Agent 4: Report Generator"]
    end

    Dashboard -->|GET /tags/live| API
    AnomalyPage -->|POST /analyze| API
    HITL -->|POST /anomalies/select-batch| API
    HypoPage -->|POST /generate-hypotheses| API
    ReportPage -->|POST /generate-reports, GET /reports/download| API
    TracePage -->|GET /trace| API
    StatsPage -->|GET /stats/correlations, /stats/causal-groups, /stats/tech-stack| API

    API --> Pipeline
    API --> Simulator
    Pipeline --> Agents
    Agents --> LLM2
    Agents --> LLM3
    Agents --> LLM4
    LLM3 --> Guardrail
    LLM4 --> Guardrail
    Agents --> Tags
    Agents --> Readings
    Agents --> AnomaliesTable
    Agents --> Traces
```

## Data Flow (Step by Step)

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant B as FastAPI
    participant P as LangGraph Pipeline
    participant A2 as Agent 2<br/>Anomaly Detector
    participant HITL as HITL Gate
    participant A3 as Agent 3<br/>Hypothesis Generator
    participant A4 as Agent 4<br/>Report Generator
    participant G as OutputGuardrail
    participant DB as PostgreSQL

    U->>F: Click "Run Analysis"
    F->>B: POST /analyze {hours: 24}
    B->>B: Clear old anomalies + traces
    B->>P: PharmaPipeline.run()

    Note over P: Pipeline goes straight to detect —<br/>no separate profiler pass

    P->>A2: detect_step(state)
    A2->>DB: Single bulk query: all readings (1 query)
    A2->>A2: Compute profiles inline (numpy)
    A2->>A2: 9 rule-based checks
    A2->>A2: Dedup by tag_id, cap at 4, priority sort
    A2-->>P: {anomalies, tag_profiles} — fast return
    A2-->>A2: Background: LLM prioritization (async)

    P->>B: Return anomalies + profiles
    B->>DB: INSERT INTO anomalies (hitl_status='pending')
    B-->>F: {anomalies_detected: 2-4, message: "Awaiting HITL"}
    F-->>U: Show anomalies, prompt review

    Note over U: Human reviews anomalies
    U->>F: Approve/reject anomalies
    F->>B: POST /anomalies/select-batch
    B->>DB: UPDATE anomalies SET hitl_status

    U->>F: Click "Generate Hypotheses"
    F->>B: POST /generate-hypotheses
    B->>A3: execute({approved_anomalies})
    A3->>A3: LLM proposes root causes
    A3->>G: guardrail.sanitize_text()
    G-->>A3: Redacted output
    A3->>DB: UPDATE anomalies SET hypothesis, recommended_action
    A3-->>B: {hypotheses, summary}
    B-->>F: Hypothesis results

    U->>F: Click "Generate Report"
    F->>B: POST /generate-reports
    B->>A4: execute({anomalies, hypotheses})
    A4->>A4: LLM writes executive narrative
    A4->>G: guardrail.sanitize_text() + check_recommendation()
    G-->>A4: Safe output
    A4->>A4: ReportLab PDF + Jinja2 HTML
    A4-->>B: {pdf_path, html_path, json_path}
    B-->>F: Report download links
```

## 3-Agent Pipeline (LangGraph)

Agent 1 (Data Profiler) was merged into Agent 2. The detector now computes statistical profiles inline from the same data cache, eliminating a full DB round-trip and LLM call.

```mermaid
stateDiagram-v2
    [*] --> Detect: POST /analyze
    Detect --> HITLGate: Anomalies found?

    HITLGate --> Hypothesize: Human approves
    HITLGate --> [*]: No anomalies → END

    Hypothesize --> Report: Agent 3 results
    Report --> [*]: PDF/HTML/JSON

    note right of Detect
        Agent 2: AnomalyDetector
        1 bulk DB query for ALL readings
        Compute profiles inline (numpy)
        9 rule-based checks
        Dedup by tag_id, cap 4
        LLM prioritization runs async
    end note

    note right of HITLGate
        Human-in-the-Loop
        between Agent 2 and 3
        Prevents AI from acting on false alarms
        FDA 21 CFR Part 11 aligned
    end note

    note right of Hypothesize
        Agent 3: HypothesisGenerator
        LLM proposes root causes
        OutputGuardrail redacts PII
    end note

    note right of Report
        Agent 4: ReportGenerator
        LLM writes executive narrative
        OutputGuardrail checks recs
        ReportLab PDF + Jinja2 HTML
    end note
```

## 9 Active Integrity Checks

```mermaid
graph LR
    subgraph RuleBased ["Deterministic Rules"]
        C1["1. Sensor Drift<br/>Rolling mean 1h vs 6h<br/>threshold: 1%/hr"]
        C2["2. Stuck Value<br/>Adaptive window,<br/>&lt;3 unique values"]
        C3["3. Impossible Readings<br/>Per-datatype limits"]
        C4["4. Rate-of-Change<br/>Type-specific thresholds<br/>10 violations"]
        C5["5. Noise Burst<br/>>&gt;5x baseline std"]
        C6["6. Correlation Breakdown<br/>Split-half Pearson r<br/>shift > 0.8"]
        C7["7. CIP Temperature Low<br/>TI-601 &lt; 70°C"]
        C8["8. FDA Audit Trail<br/>>&gt;50% non-Good QC"]
        C9["9. Cross-Sensor Inconsistency<br/>Segmented correlation + trend"]
    end

    C1 --> LLM["LLM prioritization<br/>(async, non-blocking)"]
    C2 --> LLM
    C3 --> LLM
    C4 --> LLM
    C5 --> LLM
    C6 --> LLM
    C7 --> LLM
    C8 --> LLM
    C9 --> LLM

    style C9 fill:#4338ca,stroke:#fff,color:#fff
    style LLM fill:#16a34a,stroke:#fff,color:#fff
```

## Cross-Sensor Corroboration (Check 9)

```mermaid
graph TD
    TI101["TI-101<br/>Reports 172°C<br/>✓ Within range<br/>✓ Good QC"]

    subgraph Witnesses ["Witness Sensors (8 tags have witness groups)"]
        PI101["PI-101↑<br/>Rising pressure<br/>(Clausius-Clapeyron)"]
        FI201["FI-201↑<br/>More cooling flow<br/>(heat compensation)"]
        LI101["LI-101↓<br/>Level dropping<br/>(boil-off from real heat)"]
    end

    TI101 -->|"Correlation drop -0.2"| PI101
    TI101 -->|"Trend contradicts"| FI201
    TI101 -->|"Trend contradicts"| LI101

    VERDICT["Silent Lie Detected<br/>TI-101 reads PLAUSIBLE but WRONG<br/>Contradicted by 3 witness sensors"]

    TI101 --> VERDICT
    Witnesses --> VERDICT

    style TI101 fill:#dc2626,stroke:#fff,color:#fff
    style VERDICT fill:#991b1b,stroke:#fff,color:#fff
    style Witnesses fill:#16a34a,stroke:#fff,color:#fff
```

## Tag Simulator Anomaly Pool

2-4 random anomalies are injected per reseed from a pool of 6 templates:

| Type | Example Tags | What It Does |
|------|-------------|-------------|
| `sensor_drift` | TI-101, PI-101, PI-502 | Gradual drift at 1-5%/hr or 0.5-2% for flow/pressure |
| `stuck_value` | VI-301, PI-401, FI-101 | Value frozen for 2-8 hours |
| `spike` | TI-101, PI-101, AI-901 | Sudden 3-8x multiplier, 1-3 data points |
| `noise_burst` | TI-201, VI-301, AI-901 | 3-8x noise for 1-4 hours |
| `silent_lie` | TI-101, TI-201, PI-101 | 2-6% offset with Good quality code (the novel check) |
| `sensor_drift` (slow) | PI-502, FI-601 | Slow drift at 0.5-2% (harder to detect) |

No tag overlap: each tag can only have one anomaly. Priority sort ensures cross_sensor_inconsistency > sensor_drift > stuck_value > others.

## TagSimulator Causal Groups

```mermaid
graph TB
    subgraph R101 ["Reactor R-101"]
        TI101["TI-101<br/>175°C"] -->|"Clausius-Clapeyron<br/>+0.05 bar/°C"| PI101["PI-101<br/>3.5 bar"]
        FI101["FI-101<br/>300 L/min"] -->|"Feed raises level<br/>+0.15%/L"| LI101["LI-101<br/>55%"]
        TI101 -->|"Reactor temp → cooling<br/>-0.8 coefficient"| FI201["FI-201<br/>500 L/min"]
    end

    subgraph HX201 ["Heat Exchanger HX-201"]
        TI201["TI-201<br/>60°C"] -->|"Heat transfer<br/>+0.9"| TI202["TI-202<br/>80°C"]
        FI201 -->|"More flow → lower temp<br/>-0.01"| TI202
    end

    subgraph P301 ["Pump P-301"]
        PI301["PI-301<br/>5.5 bar"] -->|"Pump curve<br/>+20"| FI301["FI-301<br/>250 L/min"]
        FI301 -->|"Vibration ~ flow<br/>+0.01"| VI301["VI-301<br/>4.2 mm/s"]
    end

    subgraph C501 ["Compressor C-501"]
        PI501["PI-501<br/>2 bar"] -->|"Compression ratio<br/>+3.0"| PI502["PI-502<br/>8 bar"]
        PI501 -->|"Compression heat<br/>+25"| TI501["TI-501<br/>115°C"]
    end

    subgraph CIP ["CIP System"]
        FI601["FI-601<br/>1000 L/min"] -->|"Better heat delivery<br/>+0.005"| TI601["TI-601<br/>77.5°C"]
        TI601 -->|"Hotter → more effective<br/>+0.5"| CI601["CI-601<br/>30 mS/cm"]
    end

    R101 -->|"LI-101 → pump demand<br/>+3.0"| P301

    style TI101 fill:#dc2626,stroke:#fff,color:#fff
```

## Performance Architecture

```mermaid
graph LR
    subgraph Before ["Before: Sequential"]
        A1_old["Agent 1: DataProfiler<br/>1 query/tag + LLM call<br/>~15-20s"]
        A2_old["Agent 2: AnomalyDetector<br/>1 query/tag + rules + LLM<br/>~10-15s"]
        Total_old["Total: ~30s"]
    end

    subgraph After ["After: Merged + Async"]
        A2_new["Agent 2: AnomalyDetector<br/>1 bulk query ALL data<br/>profiles computed inline<br/>rules + async LLM<br/>~5-8s"]
        Total_new["Total: ~5-8s"]
    end

    A1_old --> A2_old --> Total_old
    A2_new --> Total_new

    style Total_old fill:#dc2626,stroke:#fff,color:#fff
    style Total_new fill:#16a34a,stroke:#fff,color:#fff
    style A1_old fill:#991b1b,stroke:#fff,color:#fff
    style A2_new fill:#166534,stroke:#fff,color:#fff
```

Key optimizations:
- **Merged profiler**: Agent 2 computes mean/std/min/max/Q1/Q3/quality_codes inline from data_cache — no separate pass
- **Single query**: `_load_all_readings()` loads ALL tag readings in one SQL query instead of per-tag loops
- **Async LLM**: Anomaly detection returns immediately; LLM prioritization runs in background via `asyncio.ensure_future`
- **Adaptive windows**: All checks compute window sizes from `86400/n` seconds per sample — works on any interval
- **Hard cap + dedup**: Max 4 anomalies, dedup by tag_id (keep highest confidence), priority-sorted

## Database Schema

```mermaid
erDiagram
    tags {
        varchar tag_id PK
        varchar tag_name
        varchar unit_type
        varchar data_type
        decimal normal_min
        decimal normal_max
        int scan_rate_sec
        text description
    }

    tag_readings {
        int id PK
        varchar tag_id FK
        timestamptz timestamp
        decimal value
        varchar quality_code
        timestamptz created_at
    }

    anomalies {
        int id PK
        varchar tag_id FK
        varchar anomaly_type
        decimal confidence
        jsonb evidence
        timestamptz detected_at
        varchar hitl_status
        text hypothesis
        text recommended_action
    }

    agent_trace {
        int id PK
        varchar agent_name
        jsonb input
        jsonb output
        timestamptz created_at
    }

    tags ||--o{ tag_readings : "has"
    tags ||--o{ anomalies : "has"
```

## OutputGuardrail

```mermaid
graph LR
    AgentOut["Agent 3/4<br/>LLM Output"] --> Guardrail

    subgraph Guardrail ["OutputGuardrail"]
        PII["PII Redaction<br/>SSN, email, phone, IP, names"]
        Pharma["Pharma-Sensitive<br/>Batch#, lot#, patient refs,<br/>formulations, proprietary"]
        Cred["Credential Redaction<br/>Passwords, API keys, tokens, secrets"]
        Danger["Dangerous Recommendations<br/>Bypass audit trail, skip calibration,<br/>disable safety systems"]
        Conf["Confidence Bounding<br/>Cap at 0.95"]
    end

    Guardrail --> SafeOutput["Sanitized Output → DB / Report"]

    style Guardrail fill:#16a34a,stroke:#fff,color:#fff
```

## Tech Stack

```mermaid
graph TB
    subgraph Frontend ["Frontend — Vercel"]
        React["React 19"]
        Vite["Vite"]
        TW["Tailwind CSS<br/>(dark mode, navy)"]
        FM["Framer Motion"]
        Axios["Axios"]
    end

    subgraph Backend ["Backend — Render"]
        FastAPI["FastAPI"]
        SQLAlchemy["SQLAlchemy 2.0<br/>(async)"]
        LangGraph["LangGraph StateGraph<br/>(v0.2.x)"]
        LangChain["LangChain"]
        NumPy["NumPy + SciPy"]
        ReportLab["ReportLab + Jinja2"]
    end

    subgraph LLM ["LLM — Groq"]
        Groq["Groq Llama 3.1 8B Instant<br/>(all agents, via langchain_openai)"]
    end

    subgraph DB ["Database — Render PostgreSQL"]
        PG["PostgreSQL"]
        AsyncPG["asyncpg 0.29"]
    end

    subgraph Guard ["Output Safety"]
        OG["OutputGuardrail<br/>(custom regex + rules)"]
    end

    React -->|API calls| FastAPI
    FastAPI --> LangGraph
    LangGraph -->|"Agent 2-4"| Groq
    LangGraph --> SQLAlchemy
    SQLAlchemy --> PG
    FastAPI --> AsyncPG
    AsyncPG --> PG
    Groq --> OG
    NumPy --> FastAPI
    ReportLab --> FastAPI

    style Groq fill:#10b981,stroke:#fff,color:#fff
    style OG fill:#16a34a,stroke:#fff,color:#fff
    style PG fill:#336791,stroke:#fff,color:#fff
```

## Deployment

```mermaid
graph LR
    User["Browser"] --> Vercel["Vercel<br/>Frontend<br/>pharma-data-integrity-inspector<br/>.vercel.app"]
    Vercel -->|"VITE_API_BASE"| Render["Render<br/>Backend<br/>pharma-data-integrity-inspector<br/>.onrender.com"]
    Render -->|"asyncpg"| RenderDB["Render<br/>PostgreSQL<br/>Frankfurt"]
    Render -->|"Groq API"| Groq["Groq<br/>Llama 3.1 8B Instant"]
```