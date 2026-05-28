-- Pharma Data Integrity Inspector Database Schema
-- PostgreSQL 18+

-- Tags table (20 pharma process tags) — reference data, not session-scoped
CREATE TABLE IF NOT EXISTS tags (
    tag_id VARCHAR(20) PRIMARY KEY,
    tag_name VARCHAR(100),
    unit_type VARCHAR(50),
    data_type VARCHAR(20),
    normal_min DECIMAL,
    normal_max DECIMAL,
    scan_rate_sec INT,
    description TEXT
);

-- Tag readings (time-series data) — session-scoped
CREATE TABLE IF NOT EXISTS tag_readings (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL DEFAULT 'default',
    tag_id VARCHAR(20) REFERENCES tags(tag_id),
    timestamp TIMESTAMPTZ NOT NULL,
    value DECIMAL,
    quality_code VARCHAR(10),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast session-scoped queries
CREATE INDEX IF NOT EXISTS idx_tag_readings_session 
ON tag_readings(session_id, tag_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_tag_readings_tag_timestamp 
ON tag_readings(tag_id, timestamp DESC);

-- Anomalies detected — session-scoped
CREATE TABLE IF NOT EXISTS anomalies (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL DEFAULT 'default',
    tag_id VARCHAR(20) REFERENCES tags(tag_id),
    anomaly_type VARCHAR(50),
    confidence DECIMAL,
    evidence JSONB,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    hitl_status VARCHAR(20) DEFAULT 'pending',
    hypothesis TEXT,
    recommended_action TEXT
);

CREATE INDEX IF NOT EXISTS idx_anomalies_session 
ON anomalies(session_id);

-- Agent trace log — session-scoped
CREATE TABLE IF NOT EXISTS agent_trace (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL DEFAULT 'default',
    agent_name VARCHAR(50),
    input JSONB,
    output JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_trace_session 
ON agent_trace(session_id);

-- Grant permissions
GRANT ALL ON ALL TABLES IN SCHEMA public TO pharma_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO pharma_user;