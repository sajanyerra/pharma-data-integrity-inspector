import asyncio
from agents.anomaly_detector import AnomalyDetector
from agents.data_profiler import DataProfiler

async def test():
    profiler = DataProfiler()
    profile_result = await profiler.execute({'hours': 24, 'tag_ids': None})
    profiles = profile_result.get('tag_profiles', {})
    print(f'Profiles: {len(profiles)} tags')
    for tid in list(profiles.keys())[:3]:
        p = profiles[tid]
        print(f'  {tid}: count={p.get("count")} mean={p.get("mean",0):.2f} std={p.get("std",0):.2f}')
    
    det = AnomalyDetector()
    result = await det.execute({'tag_profiles': profiles, 'hours': 24})
    anomalies = result.get('anomalies', [])
    print(f'Anomalies: {len(anomalies)}')
    for a in anomalies:
        print(f'  {a.get("tag_id")} {a.get("anomaly_type")} conf={a.get("confidence",0):.2f}')
    await det.disconnect_db()

asyncio.run(test())
