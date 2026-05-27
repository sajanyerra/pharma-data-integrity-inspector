import asyncio
from agents.anomaly_detector import AnomalyDetector
from agents.data_profiler import DataProfiler

async def test():
    profiler = DataProfiler()
    profile_result = await profiler.execute({'hours': 24, 'tag_ids': None})
    profiles = profile_result.get('tag_profiles', {})
    print(f'Profiles: {len(profiles)} tags')
    
    det = AnomalyDetector()
    result = await det.execute({'tag_profiles': profiles, 'hours': 24})
    anomalies = result.get('anomalies', [])
    print(f'Anomalies: {len(anomalies)}')
    for a in anomalies:
        tid = a.get('tag_id', '?')
        atype = a.get('anomaly_type', '?')
        conf = a.get('confidence', 0)
        print(f'  {tid} {atype} conf={conf}')
    await det.disconnect_db()

asyncio.run(test())
