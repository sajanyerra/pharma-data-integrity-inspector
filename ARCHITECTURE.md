# Pharma Data Integrity Inspector — Architecture

## System Overview

```mermaid
graph TB
    subgraph Frontend ["React + Vite + Tailwind"]
        Dashboard["Dashboard<br/>Live tag values"]
        AnomalyPage["Anomaly Detection<br/>11 checks + results"]
        HITL["HITL Review<br/>Approve / Reject"]
        HypoPage["Hypothesis View<br/>Root causes"]
        ReportPage["Report Preview<br/>PDF / HTML / JSON"]
        TracePage["Trace View<br/>Agent I/O logs"]
        StatsPage["Stats for Nerds<br/>Correlations + tech stack"]
    end

    subgraph Backend ["FastAPI Backend"]
        API["REST API<br/>/analyze, /anomalies, /tags, etc."]
        Pipeline["LangGraph StateGraph<br/>4-Agent Pipeline"]
        Agents["Agent Layer"]
        Guardrail["OutputGuardrail<br/>PII / pharma / credentials"]
        Simulator["TagSimulator<br/>20 tags, causal couplings, Silent Lie"]
    end

    subgraph Database ["PostgreSQL"]
        Tags["tags<br/>20 pharma sensor configs"]
        Readings["tag_readings<br/>24h historical data"]
        AnomaliesTable["anomalies<br/>JSONB evidence, HITL status"]
        Traces["agent_trace<br/>LLM input/output logs"]
    end

    subgraph LLM ["OpenAI GPT-4o"]
        GPT1["Agent 1: Data Profiler"]
        GPT2["Agent 2: Anomaly Detector"]
        GPT3["Agent 3: Hypothesis Generator"]
        GPT4["Agent 4: Report Generator"]
    end

    subgraph Observability ["LangSmith (EU)"]
        Traces["Trace logs<br/>per-agent timing, tokens, I/O"]
    end

    Dashboard -->|GET /tags/streaming| API
    AnomalyPage -->|POST /analyze| API
    HITL -->|POST /anomalies/select-batch| API
    HypoPage -->|POST /generate-hypotheses| API
    ReportPage -->|POST /generate-reports, GET /reports/download| API
    TracePage -->|GET /trace| API
    StatsPage -->|GET /stats/correlations, /stats/causal-groups, /stats/tech-stack| API

    API --> Pipeline
    API --> Simulator
    Pipeline --> Agents
    Agents --> GPT1
    Agents --> GPT2
    Agents --> GPT3
    Agents --> GPT4
    GPT3 --> Guardrail
    GPT4 --> Guardrail
    Agents --> Tags
    Agents --> Readings
    Agents --> AnomaliesTable
    Agents --> Traces
    API --> Tags
    API --> Readings
    API --> AnomaliesTable
    API --> Traces

    GPT1 -.->|LangSmith callback| Traces
    GPT2 -.->|LangSmith callback| Traces
    GPT3 -.->|LangSmith callback| Traces
    GPT4 -.->|LangSmith callback| Traces
```

## Data Flow (Step by Step)

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant B as FastAPI
    participant P as LangGraph Pipeline
    participant A1 as Agent 1<br/>Data Profiler
    participant A2 as Agent 2<br/>Anomaly Detector
    participant HITL as HITL Gate
    participant A3 as Agent 3<br/>Hypothesis Generator
    participant A4 as Agent 4<br/>Report Generator
    participant G as OutputGuardrail
    participant DB as PostgreSQL

    U->>F: Click "Run Analysis"
    F->>B: POST /analyze {hours: 24}
    B->>P: PharmaPipeline.run()
    
    Note over P: LangGraph StateGraph executes agents sequentially
    
    P->>A1: profile_step(state)
    A1->>DB: SELECT tag_readings (24h)
    A1->>A1: numpy mean/std/quartiles per tag
    A1->>A1: GPT interprets data quality
    A1-->>P: {tag_profiles, current_step: "profiled"}
    
    P->>A2: detect_step(state)
    A2->>DB: SELECT tag_readings per tag
    A2->>A2: 11 integrity checks (rules)
    A2->>A2: GPT prioritizes anomalies
    A2-->>P: {anomalies, hitl_required: true}
    
    P->>B: Return anomalies + profiles
    B->>DB: INSERT INTO anomalies (hitl_status='pending')
    B-->>F: {anomalies_detected: 3, message: "Awaiting HITL"}
    F-->>U: Show anomalies, prompt review

    Note over U: Human reviews anomalies
    U->>F: Approve/reject anomalies
    F->>B: POST /anomalies/select-batch
    B->>DB: UPDATE anomalies SET hitl_status
    
    U->>F: Click "Generate Hypotheses"
    F->>B: POST /generate-hypotheses
    B->>A3: execute({approved_anomalies})
    A3->>A3: GPT proposes root causes
    A3->>G: guardrail.sanitize_text()
    G-->>A3: Redacted output
    A3->>DB: UPDATE anomalies SET hypothesis, recommended_action
    A3-->>B: {hypotheses, summary}
    B-->>F: Hypothesis results
    
    U->>F: Click "Generate Report"
    F->>B: POST /generate-reports
    B->>A4: execute({anomalies, hypotheses})
    A4->>A4: GPT writes executive narrative
    A4->>G: guardrail.sanitize_text() + check_recommendation()
    G-->>A4: Safe output
    A4->>A4: ReportLab PDF + Jinja2 HTML
    A4-->>B: {pdf_path, html_path, json_path}
    B-->>F: Report download links
```

## 4-Agent Pipeline (LangGraph)

```mermaid
stateDiagram-v2
    [*] --> Profile: POST /analyze
    Profile --> Detect: Agent 1 results
    Detect --> HITLGate: Anomalies found?
    
    HITLGate --> Hypothesize: Human approves
    HITLGate --> [*]: No anomalies → END
    
    Hypothesize --> Report: Agent 3 results
    Report --> [*]: PDF/HTML/JSON
    
    note right of Profile
        Agent 1: DataProfiler
        Reads 24h readings from DB
        Computes stats with numpy
        GPT interprets quality signals
    end note
    
    note right of Detect
        Agent 2: AnomalyDetector
        11 rule-based checks
        Including Cross-Sensor Corroboration
        GPT prioritizes and explains
    end note
    
    note right of HITLGate
        Human-in-the-Loop
        between Agent 2 and 3
        Prevents AI from acting on false alarms
    end note
    
    note right of Hypothesize
        Agent 3: HypothesisGenerator
        GPT proposes root causes
        OutputGuardrail redacts PII
    end note
    
    note right of Report
        Agent 4: ReportGenerator
        GPT writes executive narrative
        OutputGuardrail checks recommendations
        ReportLab PDF + Jinja2 HTML
    end note
```

## 11 Integrity Checks

```mermaid
graph LR
    subgraph RuleBased ["Deterministic Rules"]
        C1["1. Sensor Drift<br/>Rolling mean comparison"]
        C2["2. Stuck Value<br/>Sliding window unique count"]
        C3["3. Impossible Readings<br/>Physical limits per type"]
        C4["4. Quality Code Mismatch<br/>IQR outliers with Good QC"]
        C5["5. Rate-of-Change<br/>Delta between 5-sec readings"]
        C6["6. Data Gaps<br/>Time gap between readings"]
        C7["7. Statistical Outliers<br/>Z-score > 5"]
        C8["8. Correlation Breakdown<br/>Pearson shift 1st vs 2nd half"]
        C9["9. CIP Temperature Low<br/>TI-601 < 70°C"]
        C10["10. FDA Audit Trail<br/>>50% non-Good QC"]
    end

    subgraph Novel ["Novel Check"]
        C11["11. Cross-Sensor Corroboration<br/>Segmented Pearson + trend direction"]
    end

    RuleBased --> LLM["GPT prioritizes<br/>findings"]
    Novel --> LLM
    
    style C11 fill:#4338ca,stroke:#fff,color:#fff
    style Novel fill:#312e81,stroke:#fff,color:#fff
```

## Cross-Sensor Corroboration (Check 11)

```mermaid
graph TD
    TI101["TI-101<br/>Reports 172°C<br/>✓ Within range<br/>✓ Good QC"]
    
    subgraph Witnesses ["Witness Sensors"]
        PI101["PI-101↑<br/>Rising pressure<br/>(Clausius-Clapeyron)"]
        FI201["FI-201↑<br/>More cooling flow<br/>(heat compensation)"]
        LI101["LI-101↓<br/>Level dropping<br/>(boil-off from real heat)"]
    end

    TI101 -->|"Correlation drop -0.2"| PI101
    TI101 -->|"Trend contradicts"| FI201
    TI101 -->|"Trend contradicts"| LI101

    VERDICT["❌ Silent Lie Detected<br/>TI-101 reads PLAUSIBLE but WRONG<br/>Contradicted by 3 witness sensors"]
    
    TI101 --> VERDICT
    Witnesses --> VERDICT

    style TI101 fill:#dc2626,stroke:#fff,color:#fff
    style VERDICT fill:#991b1b,stroke:#fff,color:#fff
    style Witnesses fill:#16a34a,stroke:#fff,color:#fff
```

## TagSimulator Causal Groups

```mermaid
graph TB
    subgraph R101 ["Reactor R-101"]
        TI101["TI-101<br/>175°C"] -->|"Clausius-Clapeyron<br/>+0.05 bar/°C"| PI101["PI-101<br/>3.5 bar"]
        FI101["FI-101<br/>300 L/min"] -->|"Feed raises level<br/>+0.15%/L"| LI101["LI-101<br/>55%"]
        TI101 -->|"Reactor temp → cooling<br/>−0.8 coefficient"| FI201["FI-201<br/>500 L/min"]
    end

    subgraph HX201 ["Heat Exchanger HX-201"]
        TI201["TI-201<br/>60°C"] -->|"Heat transfer<br/>+0.9"| TI202["TI-202<br/>80°C"]
        FI201 -->|"More flow → lower temp<br/>−0.01"| TI202
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
        TW["Tailwind CSS<br/>(dark mode)"]
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

    subgraph LLM ["LLM"]
        OpenAI["OpenAI GPT-4o<br/>(all 4 agents)"]
    end

    subgraph DB ["Database — Render PostgreSQL"]
        PG["PostgreSQL"]
        AsyncPG["asyncpg 0.29"]
    end

    subgraph Observability ["Tracing"]
        LangSmith["LangSmith (EU)"]
    end

    subgraph Guard ["Output Safety"]
        OG["OutputGuardrail<br/>(custom regex + rules)"]
    end

    React -->|API calls| FastAPI
    FastAPI --> LangGraph
    LangGraph -->|"Agent 1-4"| OpenAI
    OpenAI -->|"callback"| LangSmith
    LangGraph --> SQLAlchemy
    SQLAlchemy --> PG
    FastAPI --> AsyncPG
    AsyncPG --> PG
    OpenAI --> OG
    NumPy --> FastAPI
    ReportLab --> FastAPI

    style OpenAI fill:#10b981,stroke:#fff,color:#fff
    style LangSmith fill:#f59e0b,stroke:#fff,color:#fff
    style OG fill:#16a34a,stroke:#fff,color:#fff
    style PG fill:#336791,stroke:#fff,color:#fff
```

## Deployment

```mermaid
graph LR
    User["Browser"] --> Vercel["Vercel<br/>Frontend<br/>pharma-data-integrity-inspector<br/>.vercel.app"]
    Vercel -->|"VITE_API_BASE"| Render["Render<br/>Backend<br/>pharma-data-integrity-inspector<br/>.onrender.com"]
    Render -->|"asyncpg"| RenderDB["Render<br/>PostgreSQL<br/>Frankfurt"]
    Render -->|"OpenAI API"| GPT["OpenAI GPT-4o"]
    Render -->|"callback"| LangSmith["LangSmith EU"]
```