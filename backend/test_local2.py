import asyncio
from datetime import datetime, timedelta
from agents.anomaly_detector import AnomalyDetector
from agents.data_profiler import DataProfiler
from tag_simulator import TagSimulator

async def test():
    # Use the SAME start_time as the seed
    data_start = datetime.utcnow() - timedelta(hours=24)
    print(f'Data start: {data_start}')
    print(f'Now: {datetime.utcnow()}')
    
    profiler = DataProfiler()
    profile_result = await profiler.execute({'hours': 24, 'tag_ids': None})
    profiles = profile_result.get('tag_profiles', {})
    print(f'Profiles: {len(profiles)} tags')
    
    det = AnomalyDetector()
    result = await det.execute({'tag_profiles': profiles, 'hours': 24})
    anomalies = result.get('anomalies', [])
    print(f'Anomalies: {len(anomalies)}')
    for a in anomalies:
        print(f'  {a.get("tag_id")} {a.get("anomaly_type")} conf={a.get("confidence",0):.2f}')
    await det.disconnect_db()

asyncio.run(test())
