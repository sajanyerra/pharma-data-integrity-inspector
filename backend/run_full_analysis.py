import asyncio
import sys
sys.path.insert(0, '.')

from agents.data_profiler import DataProfiler
from agents.anomaly_detector import AnomalyDetector

async def run_analysis():
    print("=" * 60)
    print("RUNNING MULTI-AGENT ANALYSIS")
    print("=" * 60)
    
    # Agent 1: Data Profiler
    print("\n[Agent 1] Profiling data...")
    profiler = DataProfiler()
    profile_result = await profiler.execute({"hours": 24})
    print("[OK] Profiled {} tags".format(profile_result['metadata']['tags_analyzed']))
    
    # Agent 2: Anomaly Detector
    print("\n[Agent 2] Detecting anomalies...")
    detector = AnomalyDetector()
    detection_result = await detector.execute({
        "tag_profiles": profile_result["tag_profiles"],
        "hours": 24
    })
    
    print("[OK] Found {} anomalies".format(len(detection_result['anomalies'])))
    
    # Save to database
    print("\n[Saving] Writing anomalies to database...")
    from database import async_session_maker
    from sqlalchemy import text
    import json
    
    async with async_session_maker() as session:
        for anomaly in detection_result["anomalies"]:
            # Handle correlation anomalies that have combined tag_ids
            tag_id = anomaly["tag_id"]
            if '-' in tag_id and tag_id not in ['TI-101', 'PI-101', 'FI-101', 'LI-101', 'TI-201', 'FI-201', 'TI-202', 'PI-301', 'FI-301', 'VI-301', 'TI-401', 'LI-401', 'PI-401', 'TI-501', 'PI-501', 'PI-502', 'TI-601', 'FI-601', 'CI-601', 'AI-901']:
                # Use first tag from correlation pair
                tag_id = tag_id.split('-')[0] + '-' + tag_id.split('-')[1]
            
            evidence_json = json.dumps(anomaly["evidence"]) if isinstance(anomaly["evidence"], dict) else '{}'
            await session.execute(
                text("""
                    INSERT INTO anomalies (tag_id, anomaly_type, confidence, evidence, hitl_status)
                    VALUES (:tag_id, :anomaly_type, :confidence, :evidence, 'pending')
                """),
                {
                    "tag_id": tag_id,
                    "anomaly_type": anomaly["anomaly_type"],
                    "confidence": float(anomaly["confidence"]),
                    "evidence": evidence_json
                }
            )
        await session.commit()
    
    print("[OK] Anomalies saved to database")
    
    # Summary
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print("Total Anomalies: {}".format(detection_result['summary']['total_anomalies']))
    print("\nBy Type:")
    for atype, count in detection_result['summary']['by_type'].items():
        print("  - {}: {}".format(atype, count))
    
    print("\nNext steps:")
    print("1. Open http://localhost:5173/standalone.html to view dashboard")
    print("2. Go to HITL Review to approve/reject anomalies")
    print("3. Generate hypotheses for approved anomalies")
    print("4. Generate reports (PDF/HTML/JSON)")

if __name__ == '__main__':
    asyncio.run(run_analysis())
