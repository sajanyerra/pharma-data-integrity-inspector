"""
Pharma Data Integrity Inspector - Backend API
FastAPI application with multi-agent orchestration
"""

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
import asyncio
import json
import uuid

from database import init_db, get_db, async_session_maker
from models import Tag, TagReading, Anomaly, AgentTrace
from config import settings
from agents.anomaly_detector import AnomalyDetector
from agents.hypothesis_generator import HypothesisGenerator
from agents.report_generator import ReportGenerator
from agents.pipeline import PharmaPipeline
from agents.guardrail import guardrail
from tag_simulator import TagSimulator


class TagReadingResponse(BaseModel):
    tag_id: str
    timestamp: datetime
    value: float
    quality_code: str
    unit: Optional[str] = None
    
    class Config:
        from_attributes = True


class AnomalyResponse(BaseModel):
    id: int
    tag_id: str
    tag_name: Optional[str] = None
    anomaly_type: str
    confidence: float
    evidence: dict
    detected_at: datetime
    hitl_status: str
    severity: Optional[str] = None
    hypothesis: Optional[str] = None
    recommended_action: Optional[str] = None
    
    class Config:
        from_attributes = True


class AnomalySelection(BaseModel):
    anomaly_id: int
    status: str
    comment: Optional[str] = None


class RunAnalysisRequest(BaseModel):
    hours: int = 24
    tag_ids: Optional[List[str]] = None


_seed_task = None
_analysis_jobs = {}


async def _seed_background():
    """Background task: clear old anomalies, then seed 24h of historical data if tag_readings is empty"""
    await asyncio.sleep(3)
    from sqlalchemy import text, select, func
    try:
        async with async_session_maker() as session:
            await session.execute(text("DELETE FROM anomalies"))
            await session.execute(text("DELETE FROM agent_trace"))
            await session.commit()
            print("[OK] Cleared old anomalies and traces")
        async with async_session_maker() as session:
            result = await session.execute(select(func.count()).select_from(TagReading))
            count = result.scalar()
            if count > 0:
                print(f"Database has {count:,} readings — skipping seed")
                return
            print("No readings found — seeding 24h of historical data (30-sec intervals)...")
            data_start = datetime.utcnow() - timedelta(hours=24)
            simulator = TagSimulator(seed=42, start_time=data_start)
            start_time = data_start
            batch_size = 1000
            batch = []
            inserted = 0
            for i in range(24 * 120):
                ts = start_time + timedelta(seconds=i * 30)
                readings = simulator.generate_all_tags(ts)
                for r in readings:
                    batch.append({
                        'tag_id': r['tag_id'],
                        'timestamp': r['timestamp'],
                        'value': r['value'],
                        'quality_code': r['quality_code']
                    })
                    if len(batch) >= batch_size:
                        await session.execute(
                            text("INSERT INTO tag_readings (tag_id, timestamp, value, quality_code) VALUES (:tag_id, :timestamp, :value, :quality_code)"),
                            batch
                        )
                        await session.commit()
                        inserted += len(batch)
                        batch = []
            if batch:
                await session.execute(
                    text("INSERT INTO tag_readings (tag_id, timestamp, value, quality_code) VALUES (:tag_id, :timestamp, :value, :quality_code)"),
                    batch
                )
                await session.commit()
                inserted += len(batch)
            print(f"[OK] Seeded {inserted:,} readings")
    except Exception as e:
        print(f"Seed error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    import os
    if settings.LANGSMITH_API_KEY:
        os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
    if settings.LANGSMITH_PROJECT:
        os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT
    os.environ["LANGSMITH_TRACING"] = "true" if settings.LANGSMITH_TRACING else "false"
    if settings.LANGSMITH_ENDPOINT:
        os.environ["LANGSMITH_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
    print(f"LangSmith tracing: {'ON' if settings.LANGSMITH_TRACING else 'OFF'} (endpoint: {settings.LANGSMITH_ENDPOINT or 'default US'})")
    print("Starting Pharma Data Integrity Inspector...")
    await init_db()
    print("Database initialized")
    global _seed_task
    _seed_task = asyncio.create_task(_seed_background())
    yield
    print("Shutting down...")


app = FastAPI(
    title="Pharma Data Integrity Inspector",
    description="AI Multi-Agent System for Pharma Data Quality",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "name": "Pharma Data Integrity Inspector",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}


@app.get("/seeding-status")
async def seeding_status():
    """Check if background data seeding is complete"""
    from sqlalchemy import select, func
    if _seed_task is not None and not _seed_task.done():
        return {"status": "seeding", "message": "Historical data is being seeded. Try again in a moment."}
    async with async_session_maker() as session:
        result = await session.execute(select(func.count()).select_from(TagReading))
        count = result.scalar()
    return {"status": "ready", "readings": count}


@app.get("/guardrail/info")
async def guardrail_info():
    """Get guardrail configuration and capabilities"""
    return {
        "enabled": True,
        "features": [
            "PII redaction (SSN, email, phone, IP, names)",
            "Pharma sensitive redaction (batch numbers, lot numbers, patient references, proprietary formulations)",
            "Credential redaction (passwords, API keys, tokens, secrets)",
            "Dangerous recommendation blocking (bypass audit trail, skip calibration, disable safety)",
            "Confidence bounding [0, 1]",
        ],
        "redacted_patterns": len(guardrail.REDACTION_PATTERNS) + len(guardrail.PHARMA_SENSITIVE_PATTERNS),
        "blocked_action_patterns": len(guardrail.BLOCKED_RECOMMENDATION_PATTERNS),
    }


@app.post("/guardrail/test")
async def guardrail_test(request: dict):
    """Test guardrail on sample text"""
    text = request.get("text", "")
    sanitized = guardrail.sanitize_text(text)
    is_safe, reason = guardrail.check_recommendation(text)
    return {
        "original": text,
        "sanitized": sanitized,
        "changed": sanitized != text,
        "is_safe": is_safe,
        "reason": reason,
    }


@app.get("/tags", response_model=List[dict])
async def get_tags():
    """Get all tag metadata"""
    async with async_session_maker() as session:
        from sqlalchemy import select
        result = await session.execute(select(Tag))
        tags = result.scalars().all()
        return [
            {
                "tag_id": t.tag_id,
                "tag_name": t.tag_name,
                "unit_type": t.unit_type,
                "data_type": t.data_type,
                "normal_min": float(t.normal_min) if t.normal_min else 0,
                "normal_max": float(t.normal_max) if t.normal_max else 0,
                "scan_rate_sec": t.scan_rate_sec,
                "description": t.description
            }
            for t in tags
        ]


@app.get("/tags/{tag_id}/readings", response_model=List[TagReadingResponse])
async def get_tag_readings(
    tag_id: str,
    hours: int = 24,
    limit: int = 1000
):
    """Get recent readings for a specific tag"""
    async with async_session_maker() as session:
        from sqlalchemy import select, desc
        
        query = (
            select(TagReading)
            .where(TagReading.tag_id == tag_id)
            .order_by(desc(TagReading.timestamp))
            .limit(limit)
        )
        
        result = await session.execute(query)
        readings = result.scalars().all()
        
        tag_result = await session.execute(
            select(Tag).where(Tag.tag_id == tag_id)
        )
        tag = tag_result.scalar()
        unit = tag.data_type if tag else None
        
        return [
            TagReadingResponse(
                tag_id=r.tag_id,
                timestamp=r.timestamp,
                value=float(r.value) if r.value else 0,
                quality_code=r.quality_code,
                unit=unit
            )
            for r in readings
        ]


@app.get("/tags/streaming")
async def get_streaming_data():
    """Get latest readings for all tags (for dashboard)"""
    async with async_session_maker() as session:
        from sqlalchemy import select, distinct
        
        # Get latest reading for each tag
        tags_result = await session.execute(select(Tag.tag_id))
        tag_ids = [row[0] for row in tags_result.fetchall()]
        
        latest_readings = []
        for tag_id in tag_ids:
            query = (
                select(TagReading)
                .where(TagReading.tag_id == tag_id)
                .order_by(TagReading.timestamp.desc())
                .limit(1)
            )
            result = await session.execute(query)
            reading = result.scalar()
            
            if reading:
                tag_info = await session.execute(
                    select(Tag.tag_name, Tag.data_type).where(Tag.tag_id == tag_id)
                )
                tag_data = tag_info.fetchone()
                
                latest_readings.append({
                    "tag_id": reading.tag_id,
                    "tag_name": tag_data[0] if tag_data else "",
                    "value": float(reading.value) if reading.value else 0,
                    "quality_code": reading.quality_code,
                    "unit": tag_data[1] if tag_data else "",
                    "timestamp": reading.timestamp.isoformat()
                })
        
        return latest_readings


@app.get("/anomalies")
async def get_anomalies(
    status: Optional[str] = None,
    limit: int = 100
):
    """Get detected anomalies with optional status filter"""
    import json as _json
    try:
        async with async_session_maker() as session:
            from sqlalchemy import select
            
            query = select(Anomaly).order_by(Anomaly.detected_at.desc()).limit(limit)
            
            if status:
                query = query.where(Anomaly.hitl_status == status)
            
            result = await session.execute(query)
            anomalies = result.scalars().all()
            
            response = []
            for a in anomalies:
                tag_info = await session.execute(
                    select(Tag.tag_name).where(Tag.tag_id == a.tag_id)
                )
                tag_name = tag_info.scalar()
                
                evidence = a.evidence or {}
                if isinstance(evidence, str):
                    try:
                        evidence = _json.loads(evidence)
                    except:
                        evidence = {}
                
                try:
                    confidence = float(a.confidence) if a.confidence else 0
                except (TypeError, ValueError):
                    confidence = 0
                
                severity = "low"
                if isinstance(evidence, dict):
                    ev_sev = evidence.get("severity")
                    if ev_sev in ("high", "medium", "low", "critical"):
                        severity = ev_sev
                    elif confidence > 0.8:
                        severity = "high"
                    elif confidence > 0.5:
                        severity = "medium"
                else:
                    if confidence > 0.8:
                        severity = "high"
                    elif confidence > 0.5:
                        severity = "medium"
                
                response.append({
                    "id": a.id,
                    "tag_id": a.tag_id,
                    "tag_name": tag_name,
                    "anomaly_type": a.anomaly_type,
                    "confidence": confidence,
                    "evidence": evidence,
                    "detected_at": a.detected_at.isoformat() if a.detected_at else None,
                    "hitl_status": a.hitl_status,
                    "severity": severity,
                    "hypothesis": a.hypothesis,
                    "recommended_action": a.recommended_action
                })
                if isinstance(evidence, dict) and evidence.get("is_silent_lie"):
                    response[-1]["evidence"]["is_silent_lie"] = True
            
            return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching anomalies: {str(e)}")


@app.post("/anomalies/select")
async def select_anomaly(selection: AnomalySelection):
    """Update HITL status for an anomaly"""
    async with async_session_maker() as session:
        from sqlalchemy import update
        
        await session.execute(
            update(Anomaly)
            .where(Anomaly.id == selection.anomaly_id)
            .values(hitl_status=selection.status)
        )
        await session.commit()
        
        return {"status": "success", "anomaly_id": selection.anomaly_id}


@app.post("/anomalies/select-batch")
async def select_anomalies_batch(selections: List[AnomalySelection]):
    """Update HITL status for multiple anomalies"""
    async with async_session_maker() as session:
        from sqlalchemy import update
        
        for selection in selections:
            await session.execute(
                update(Anomaly)
                .where(Anomaly.id == selection.anomaly_id)
                .values(hitl_status=selection.status)
            )
        
        await session.commit()
        return {"status": "success", "updated_count": len(selections)}


@app.post("/analyze")
async def run_analysis(request: RunAnalysisRequest):
    """Start analysis in background. Returns job_id immediately."""
    job_id = str(uuid.uuid4())[:8]
    _analysis_jobs[job_id] = {"status": "running", "progress": "Starting pipeline...", "result": None, "error": None}
    
    async def _run():
        try:
            print(f"[Analyze] Starting pipeline for job {job_id}...")
            pipeline = PharmaPipeline()
            result = await pipeline.run({
                "hours": request.hours,
                "tag_ids": request.tag_ids
            })
            
            num_anomalies = len(result.get("anomalies", []))
            print(f"[Analyze] Pipeline found {num_anomalies} anomalies")
            _analysis_jobs[job_id]["progress"] = f"Found {num_anomalies} anomalies, saving..."
            
            async with async_session_maker() as session:
                from sqlalchemy import text
                await session.execute(text("DELETE FROM anomalies"))
                await session.commit()
            
            async with async_session_maker() as session:
                from sqlalchemy import text
                for anomaly in result["anomalies"]:
                    evidence = anomaly.get("evidence", {})
                    if not isinstance(evidence, dict):
                        evidence = {}
                    evidence_clean = {}
                    for k, v in evidence.items():
                        if hasattr(v, 'item'):
                            evidence_clean[k] = v.item()
                        elif isinstance(v, (int, float, str, bool, type(None))):
                            evidence_clean[k] = v
                        elif isinstance(v, (list, dict)):
                            evidence_clean[k] = v
                        else:
                            evidence_clean[k] = str(v)
                    
                    if anomaly.get("is_silent_lie"):
                        evidence_clean["is_silent_lie"] = True
                    if anomaly.get("pharma_impact"):
                        evidence_clean["pharma_impact"] = anomaly["pharma_impact"]
                    if anomaly.get("severity"):
                        evidence_clean["severity"] = anomaly["severity"]
                    
                    await session.execute(
                        text("""
                            INSERT INTO anomalies (tag_id, anomaly_type, confidence, evidence, hitl_status)
                            VALUES (:tag_id, :anomaly_type, :confidence, :evidence, 'pending')
                        """),
                        {
                            "tag_id": anomaly["tag_id"],
                            "anomaly_type": anomaly["anomaly_type"],
                            "confidence": float(anomaly["confidence"]),
                            "evidence": json.dumps(evidence_clean)
                        }
                    )
                await session.commit()
            
            _analysis_jobs[job_id] = {
                "status": "completed",
                "progress": "Done",
                "result": {
                    "status": "success",
                    "anomalies_detected": len(result["anomalies"]),
                    "message": f"LangGraph pipeline: {len(result['anomalies'])} anomalies detected. Review in HITL view."
                },
                "error": None
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            _analysis_jobs[job_id] = {
                "status": "failed",
                "progress": "Failed",
                "result": None,
                "error": str(e)
            }
    
    asyncio.create_task(_run())
    return {"job_id": job_id, "status": "started"}


@app.post("/reseed")
async def reseed_data():
    """Clear and reseed all data with fresh 24h of historical data (30-sec intervals)"""
    from sqlalchemy import text as sa_text
    try:
        async with async_session_maker() as session:
            await session.execute(sa_text("DELETE FROM anomalies"))
            await session.execute(sa_text("DELETE FROM agent_trace"))
            await session.execute(sa_text("DELETE FROM tag_readings"))
            await session.commit()
        
        simulator = TagSimulator(seed=42, start_time=datetime.utcnow() - timedelta(hours=24))
        start_time = datetime.utcnow() - timedelta(hours=24)
        batch_size = 2000
        batch = []
        inserted = 0
        async with async_session_maker() as session:
            for i in range(24 * 120):
                ts = start_time + timedelta(seconds=i * 30)
                readings = simulator.generate_all_tags(ts)
                for r in readings:
                    batch.append({
                        'tag_id': r['tag_id'],
                        'timestamp': r['timestamp'],
                        'value': r['value'],
                        'quality_code': r['quality_code']
                    })
                    if len(batch) >= batch_size:
                        await session.execute(
                            sa_text("INSERT INTO tag_readings (tag_id, timestamp, value, quality_code) VALUES (:tag_id, :timestamp, :value, :quality_code)"),
                            batch
                        )
                        await session.commit()
                        inserted += len(batch)
                        batch = []
            if batch:
                await session.execute(
                    sa_text("INSERT INTO tag_readings (tag_id, timestamp, value, quality_code) VALUES (:tag_id, :timestamp, :value, :quality_code)"),
                    batch
                )
                await session.commit()
                inserted += len(batch)
        
        return {"status": "success", "readings_seeded": inserted}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
async def run_analysis_sync(request: RunAnalysisRequest):
    """Synchronous analysis for debugging"""
    try:
        pipeline = PharmaPipeline()
        result = await pipeline.run({
            "hours": request.hours,
            "tag_ids": request.tag_ids
        })
        anomalies = result.get("anomalies", [])
        profiles = result.get("tag_profiles", {})
        
        # Debug: show profile stats for first 3 tags
        debug_info = {}
        for tid in list(profiles.keys())[:3]:
            p = profiles[tid]
            debug_info[tid] = {"count": p.get("count"), "mean": p.get("mean"), "std": p.get("std")}
        
        return {
            "status": "success",
            "anomalies_detected": len(anomalies),
            "anomalies": [
                {"tag_id": a.get("tag_id"), "anomaly_type": a.get("anomaly_type"), "confidence": float(a.get("confidence", 0))}
                for a in anomalies
            ],
            "tag_profiles_count": len(profiles),
            "debug_profiles": debug_info,
            "current_step": result.get("current_step"),
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analyze/status/{job_id}")
async def get_analysis_status(job_id: str):
    """Poll for analysis job status"""
    if job_id not in _analysis_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _analysis_jobs[job_id]


@app.post("/analyze-sync")
async def run_analysis_sync(request: RunAnalysisRequest):
    """Synchronous analysis for debugging"""
    try:
        pipeline = PharmaPipeline()
        result = await pipeline.run({
            "hours": request.hours,
            "tag_ids": request.tag_ids
        })
        anomalies = result.get("anomalies", [])
        profiles = result.get("tag_profiles", {})
        
        debug_info = {}
        for tid in list(profiles.keys())[:5]:
            p = profiles[tid]
            debug_info[tid] = {"count": p.get("count"), "mean": round(p.get("mean", 0), 2), "std": round(p.get("std", 0), 2)}
        
        return {
            "status": "success",
            "anomalies_detected": len(anomalies),
            "anomalies": [
                {"tag_id": a.get("tag_id"), "anomaly_type": a.get("anomaly_type"), "confidence": float(a.get("confidence", 0)), "evidence_keys": list(a.get("evidence", {}).keys())}
                for a in anomalies
            ],
            "tag_profiles_count": len(profiles),
            "debug_profiles": debug_info,
            "current_step": result.get("current_step"),
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


async def _wait_for_seed():
    """Wait for background seeding to complete if it's running"""
    if _seed_task is not None and not _seed_task.done():
        await _seed_task


@app.post("/generate-hypotheses")
async def generate_hypotheses():
    """Start hypothesis generation in background. Returns job_id immediately."""
    job_id = str(uuid.uuid4())[:8]
    _analysis_jobs[job_id] = {"status": "running", "progress": "Loading approved anomalies...", "result": None, "error": None}
    
    async def _run():
        try:
            async with async_session_maker() as session:
                from sqlalchemy import text
                import json
                
                _analysis_jobs[job_id]["progress"] = "Running Agent 3: Hypothesis Generator..."
                result = await session.execute(text("SELECT * FROM anomalies WHERE hitl_status = 'approved'"))
                
                anomalies = []
                for row in result.fetchall():
                    row_dict = dict(row._mapping)
                    if isinstance(row_dict.get('evidence'), str):
                        try:
                            row_dict['evidence'] = json.loads(row_dict['evidence'])
                        except:
                            row_dict['evidence'] = {}
                    if 'confidence' in row_dict and row_dict['confidence'] is not None:
                        row_dict['confidence'] = float(row_dict['confidence'])
                    row_dict.setdefault('severity', 'medium')
                    anomalies.append(row_dict)
                
                if not anomalies:
                    result = await session.execute(text("SELECT * FROM anomalies WHERE hitl_status != 'rejected'"))
                    anomalies = []
                    for row in result.fetchall():
                        row_dict = dict(row._mapping)
                        if isinstance(row_dict.get('evidence'), str):
                            try:
                                row_dict['evidence'] = json.loads(row_dict['evidence'])
                            except:
                                row_dict['evidence'] = {}
                        if 'confidence' in row_dict and row_dict['confidence'] is not None:
                            row_dict['confidence'] = float(row_dict['confidence'])
                        row_dict.setdefault('severity', 'medium')
                        anomalies.append(row_dict)
                
                if not anomalies:
                    _analysis_jobs[job_id] = {"status": "completed", "progress": "Done", "result": {"status": "no_anomalies", "hypotheses": [], "message": "All anomalies were rejected. You can still generate a report."}, "error": None}
                    return
                
                generator = HypothesisGenerator()
                hypothesis_result = await generator.execute({
                    "anomalies": anomalies
                })
                
                await session.commit()
                
                _analysis_jobs[job_id] = {
                    "status": "completed",
                    "progress": "Done",
                    "result": {
                        "status": "success",
                        "hypotheses": hypothesis_result["hypotheses"],
                        "summary": hypothesis_result["summary"]
                    },
                    "error": None
                }
        except Exception as e:
            _analysis_jobs[job_id] = {"status": "failed", "progress": "Failed", "result": None, "error": str(e)}
    
    asyncio.create_task(_run())
    return {"job_id": job_id, "status": "started"}


@app.post("/generate-reports")
async def generate_reports():
    """Start report generation in background. Returns job_id immediately."""
    job_id = str(uuid.uuid4())[:8]
    _analysis_jobs[job_id] = {"status": "running", "progress": "Loading anomalies...", "result": None, "error": None}
    
    async def _run():
        try:
            async with async_session_maker() as session:
                from sqlalchemy import text
                import json
                _analysis_jobs[job_id]["progress"] = "Running Agent 4: Report Generator..."
                result = await session.execute(text("""
                    SELECT a.*, t.tag_name
                    FROM anomalies a
                    JOIN tags t ON a.tag_id = t.tag_id
                    ORDER BY a.detected_at DESC
                """))
                anomalies = [dict(row._mapping) for row in result.fetchall()]
                
                for a in anomalies:
                    if 'confidence' in a and a['confidence'] is not None:
                        a['confidence'] = float(a['confidence'])
                    if 'evidence' in a and isinstance(a['evidence'], str):
                        try:
                            a['evidence'] = json.loads(a['evidence'])
                        except:
                            a['evidence'] = {}
                    if not a.get('severity'):
                        ev = a.get('evidence', {})
                        if isinstance(ev, dict) and 'severity' in ev:
                            a['severity'] = ev['severity']
                        else:
                            conf = a.get('confidence', 0.5)
                            a['severity'] = 'high' if conf > 0.8 else 'medium' if conf > 0.5 else 'low'
                
                if not anomalies:
                    anomalies = []
                
                report_gen = ReportGenerator()
                report_result = await report_gen.execute({
                    "anomalies": anomalies,
                    "hypotheses": [{"tag_id": a["tag_id"], "root_cause": a.get("hypothesis", ""), "recommended_action": a.get("recommended_action", ""), "confidence": float(a.get("confidence") or 0), "anomaly_id": a.get("id"), "alternative_causes": [], "pharma_impact": ""} for a in anomalies]
                })
                
                _analysis_jobs[job_id] = {
                    "status": "completed",
                    "progress": "Done",
                    "result": {
                        "status": "success",
                        "reports": {
                            "pdf": report_result["pdf_path"],
                            "html": report_result["html_path"],
                            "json": report_result["json_path"]
                        }
                    },
                    "error": None
                }
        except Exception as e:
            _analysis_jobs[job_id] = {"status": "failed", "progress": "Failed", "result": None, "error": str(e)}
    
    asyncio.create_task(_run())
    return {"job_id": job_id, "status": "started"}


@app.get("/reports/download/{report_type}")
async def download_report(report_type: str):
    """Download latest report"""
    from pathlib import Path
    
    reports_dir = Path(__file__).parent.parent / "reports"
    
    if not reports_dir.exists():
        raise HTTPException(status_code=404, detail="No reports found")
    
    # Get latest report of specified type
    pattern = f"*.{report_type.lower()}"
    reports = list(reports_dir.glob(pattern))
    
    if not reports:
        raise HTTPException(status_code=404, detail=f"No {report_type} reports found")
    
    latest_report = max(reports, key=lambda p: p.stat().st_mtime)
    
    return FileResponse(
        str(latest_report),
        media_type="application/octet-stream" if report_type == "json" else "text/html" if report_type == "html" else "application/pdf",
        filename=latest_report.name
    )


@app.get("/trace")
async def get_agent_trace(limit: int = 100):
    """Get agent execution trace"""
    async with async_session_maker() as session:
        from sqlalchemy import select, desc
        
        query = (
            select(AgentTrace)
            .order_by(desc(AgentTrace.created_at))
            .limit(limit)
        )
        
        result = await session.execute(query)
        traces = result.scalars().all()
        
        return [
            {
                "id": t.id,
                "agent_name": t.agent_name,
                "input": t.input,
                "output": t.output,
                "created_at": t.created_at.isoformat()
            }
            for t in traces
        ]


@app.delete("/anomalies/clear")
async def clear_anomalies():
    """Clear all anomalies (for demo reset)"""
    try:
        async with async_session_maker() as session:
            from sqlalchemy import text
            await session.execute(text("DELETE FROM anomalies"))
            await session.commit()
            return {"status": "success", "message": "All anomalies cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tags/live")
async def get_live_tags():
    """Get live simulated tag values merged with metadata"""
    from datetime import datetime
    simulator = TagSimulator()
    readings = simulator.generate_all_tags(datetime.now())
    metadata = simulator.get_tag_metadata()
    meta_map = {m["tag_id"]: m for m in metadata}
    for r in readings:
        m = meta_map.get(r["tag_id"], {})
        r["tag_name"] = m.get("tag_name", r["tag_id"])
        r["data_type"] = m.get("data_type", "")
        r["unit_type"] = m.get("unit_type", "")
        r["normal_min"] = m.get("normal_min", 0)
        r["normal_max"] = m.get("normal_max", 0)
    return readings


@app.post("/reset")
async def full_reset():
    """Reset everything: clear anomalies, hypotheses, and agent traces"""
    try:
        async with async_session_maker() as session:
            from sqlalchemy import text
            await session.execute(text("DELETE FROM anomalies"))
            await session.execute(text("DELETE FROM agent_trace"))
            await session.commit()
            return {"status": "success", "message": "Full reset complete"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats/correlations")
async def get_correlation_matrix():
    """Compute live pairwise Pearson correlations for all correlated tag pairs"""
    try:
        from scipy import stats as sp_stats
        import numpy as np
        from datetime import datetime as dt
        from datetime import timedelta as td
        from sqlalchemy import text as sa_text
        cutoff = dt.utcnow() - td(hours=24)
        
        simulator = TagSimulator()
        pairs = simulator.CORRELATED_PAIRS
        results = []
        
        async with async_session_maker() as session:
            for tag_a, tag_b in pairs:
                rows = await session.execute(
                    sa_text("""
                        SELECT a.value AS va, b.value AS vb
                        FROM tag_readings a
                        JOIN tag_readings b ON a.timestamp = b.timestamp AND a.tag_id = :ta AND b.tag_id = :tb
                        WHERE a.timestamp >= :cutoff
                        ORDER BY a.timestamp
                        LIMIT 2000
                    """),
                    {"ta": tag_a, "tb": tag_b, "cutoff": cutoff}
                )
                all_pairs = rows.fetchall()
                n = len(all_pairs)
                
                if n < 50:
                    results.append({"pair": f"{tag_a} \u2194 {tag_b}", "tag_a": tag_a, "tag_b": tag_b, "correlation": None, "p_value": None, "n": n})
                    continue
                
                a_vals = np.array([float(p[0]) for p in all_pairs])
                b_vals = np.array([float(p[1]) for p in all_pairs])
                
                if np.std(a_vals) == 0 or np.std(b_vals) == 0:
                    results.append({"pair": f"{tag_a} \u2194 {tag_b}", "tag_a": tag_a, "tag_b": tag_b, "correlation": 0, "p_value": 1.0, "n": n})
                    continue
                
                corr, pval = sp_stats.pearsonr(a_vals, b_vals)
                
                results.append({
                    "pair": f"{tag_a} \u2194 {tag_b}",
                    "tag_a": tag_a,
                    "tag_b": tag_b,
                    "correlation": round(float(corr), 4),
                    "p_value": round(float(pval), 6),
                    "n": n,
                })
        
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    return results


@app.get("/stats/causal-groups")
async def get_causal_groups():
    """Return the causal group definitions and coupling coefficients"""
    simulator = TagSimulator()
    groups = simulator.get_causal_groups()
    silent_lie = simulator.get_silent_lie_config()
    return {
        "causal_groups": groups,
        "correlated_pairs": simulator.CORRELATED_PAIRS,
        "silent_lie": silent_lie,
        "tag_count": len(simulator.TAG_CONFIGS),
        "description": "Cross-tag causal relationships model physics-based coupling in the simulated pharma plant."
    }


@app.get("/stats/integrity-checks")
async def get_integrity_checks():
    """Return metadata about all 11 integrity checks"""
    return [
        {
            "id": 1, "name": "Sensor Drift", "method": "Rolling mean comparison (1h vs 6h)",
            "detects": "Gradual calibration degradation", "threshold": ">1% deviation per hour",
            "is_rule_based": True
        },
        {
            "id": 2, "name": "Stuck Value", "method": "Unique value count in 1h window",
            "detects": "Transmitter stopped updating", "threshold": "<3 unique values in 720 readings",
            "is_rule_based": True
        },
        {
            "id": 3, "name": "Impossible Readings", "method": "Physical limits per data type",
            "detects": "Sensor reading outside physical possibility", "threshold": "e.g. T < -273.15°C",
            "is_rule_based": True
        },
        {
            "id": 4, "name": "Quality Code Mismatch", "method": "IQR outlier check vs quality_code='Good'",
            "detects": "SCADA reports Good but data is outlier", "threshold": ">5% outliers with >90% Good quality",
            "is_rule_based": True
        },
        {
            "id": 5, "name": "Rate-of-Change", "method": "Delta between consecutive 5-sec readings",
            "detects": "Physically impossible step changes", "threshold": "e.g. >50°C per 5 sec",
            "is_rule_based": True
        },
        {
            "id": 6, "name": "Data Gaps", "method": "Time gap between consecutive readings",
            "detects": "Missing data in historian", "threshold": ">10 seconds (2x scan rate)",
            "is_rule_based": True
        },
        {
            "id": 7, "name": "Statistical Outliers", "method": "Z-score > 5 (extreme outliers only)",
            "detects": "Extreme value deviations", "threshold": ">5 sigma, >5% of readings",
            "is_rule_based": True
        },
        {
            "id": 8, "name": "Correlation Breakdown", "method": "Pearson correlation shift (1st half vs 2nd half)",
            "detects": "Tag pairs that stopped correlating mid-period", "threshold": "Shift > 0.4",
            "is_rule_based": True
        },
        {
            "id": 9, "name": "CIP Temperature Low", "method": "CIP supply temp < sterilization threshold",
            "detects": "Incomplete cleaning cycle", "threshold": "TI-601 < 70°C for >10 readings",
            "is_rule_based": True
        },
        {
            "id": 10, "name": "FDA Audit Trail", "method": "Quality code distribution check",
            "detects": "21 CFR Part 11 compliance concern", "threshold": ">50% non-Good quality codes",
            "is_rule_based": True
        },
        {
            "id": 11, "name": "Cross-Sensor Corroboration", "method": "Segmented Pearson correlation + trend direction analysis against witness sensors",
            "detects": "Sensor reading is PLAUSIBLE but WRONG — contradicted by correlated sensors",
            "threshold": "Correlation drop > 0.2 with contradicted trend direction",
            "is_rule_based": True,
            "is_novel": True,
            "why_novel": "No historian or analytics product detects sensors that are wrong-but-plausible. This check cross-references physically-correlated sensors — the same logic a process engineer uses on a whiteboard."
        },
    ]


@app.get("/stats/pipeline")
async def get_pipeline_info():
    """Return pipeline architecture for the Stats page"""
    return {
        "orchestration": "LangGraph StateGraph (v0.2.x) with conditional HITL edge",
        "agents": [
            {
                "id": 1, "name": "Data Profiler", "engine": "SQLAlchemy + numpy + ChatOpenAI",
                "flow": "Read tag_readings → compute mean/std/quartiles → GPT interprets data quality"
            },
            {
                "id": 2, "name": "Anomaly Detector", "engine": "scipy.stats + numpy + ChatOpenAI",
                "flow": "11 integrity checks (rules) → GPT analyzes pattern of findings"
            },
            {
                "id": 3, "name": "Hypothesis Generator", "engine": "ChatOpenAI + PromptTemplate + OutputGuardrail",
                "flow": "Approved anomalies → GPT proposes root causes → guardrail redacts PII"
            },
            {
                "id": 4, "name": "Report Generator", "engine": "Jinja2 + ChatOpenAI + OutputGuardrail",
                "flow": "All evidence → GPT writes executive narrative → PDF/HTML/JSON output"
            },
        ],
        "guardrail": {
            "name": "OutputGuardrail",
            "checks": ["PII redaction (SSN, email, phone, IP, names)", "Pharma-sensitive (batch/lot numbers, patient refs)", "Credential redaction", "Dangerous recommendation blocking", "Confidence bounding (cap at 0.95)"],
            "applied_to": ["Agent 3 (hypothesis output)", "Agent 4 (report data)"]
        },
        "hitl": {
            "name": "Human-in-the-Loop Gate",
            "position": "Between Agent 2 and Agent 3",
            "purpose": "Human must approve anomalies before AI generates root causes — prevents AI from acting on false alarms",
            "statuses": ["pending → approved → hypothesis generated", "pending → rejected → no action"]
        },
        "silent_lie": {
            "concept": "A sensor that reads within normal range but is wrong. Passes quality codes, passes threshold checks, but contradicts its correlated sensors.",
            "example": "TI-101 reports 172°C (within 150-200 range, Good quality). But PI-101 trends up (suggesting 175°C+) and FI-201 rises (cooling compensating for heat you don't see). The sensor is wrong.",
            "detection": "Check 11: segmented window correlation + trend direction analysis against witness sensors"
        }
    }


@app.get("/stats/tech-stack")
async def get_tech_stack():
    return [
        {
            "category": "LLM & Orchestration",
            "items": [
                {"name": "OpenAI GPT-4o", "role": "LLM reasoning engine for all 4 agents", "icon": "Brain"},
                {"name": "LangChain", "role": "Prompt templates, output parsers, agent tool framework", "icon": "Link2"},
                {"name": "LangGraph", "role": "StateGraph orchestration — conditional HITL edge between Agent 2 and 3", "icon": "GitBranch"},
                {"name": "LangSmith", "role": "Trace logging, evaluation, and debug (EU endpoint)", "icon": "Activity"},
            ]
        },
        {
            "category": "Backend Framework",
            "items": [
                {"name": "FastAPI", "role": "Async REST API with Pydantic models", "icon": "Zap"},
                {"name": "Uvicorn", "role": "ASGI server with hot-reload", "icon": "Server"},
                {"name": "SQLAlchemy 2.0", "role": "Async PostgreSQL ORM", "icon": "Database"},
                {"name": "Pydantic v2", "role": "Schema validation and settings management", "icon": "Shield"},
            ]
        },
        {
            "category": "Data & Math",
            "items": [
                {"name": "NumPy", "role": "Array ops, rolling windows, autocorrelation", "icon": "BarChart3"},
                {"name": "SciPy", "role": "Pearson correlation, p-values, statistical tests", "icon": "TrendingUp"},
                {"name": "Pandas", "role": "DataFrame operations on sensor data", "icon": "Table"},
            ]
        },
        {
            "category": "Output Safety",
            "items": [
                {"name": "OutputGuardrail", "role": "Custom — PII redaction, pharma-sensitive blocking, confidence bounding", "icon": "Shield"},
                {"name": "Regex + pattern matching", "role": "SSN/phone/email/IP/batch number detection", "icon": "Search"},
            ]
        },
        {
            "category": "Reporting",
            "items": [
                {"name": "ReportLab", "role": "PDF generation", "icon": "FileText"},
                {"name": "Jinja2", "role": "HTML report templating", "icon": "Code"},
            ]
        },
        {
            "category": "Frontend",
            "items": [
                {"name": "React 19", "role": "UI framework", "icon": "Component"},
                {"name": "Vite", "role": "Build tool and dev server", "icon": "Zap"},
                {"name": "Tailwind CSS", "role": "Utility-first styling with dark mode", "icon": "Palette"},
                {"name": "Framer Motion", "role": "Animations and transitions", "icon": "Play"},
                {"name": "Axios", "role": "HTTP client for API calls", "icon": "Globe"},
            ]
        },
        {
            "category": "Infrastructure",
            "items": [
                {"name": "PostgreSQL", "role": "Primary database — readings, anomalies, traces, hypotheses", "icon": "Database"},
                {"name": "asyncpg", "role": "Async PostgreSQL driver", "icon": "Server"},
            ]
        },
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )
