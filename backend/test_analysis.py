import asyncio
import sys
sys.path.insert(0, '.')

from agents.data_profiler import DataProfiler

async def test():
    print("Testing Data Profiler Agent...")
    profiler = DataProfiler()
    
    try:
        result = await profiler.execute({"hours": 24})
        print("[OK] Success! Analyzed {} tags".format(result['metadata']['tags_analyzed']))
        print("  Analysis window: {} hours".format(result['metadata']['analysis_window_hours']))
        
        # Show first 3 tag profiles
        for tag_id in list(result['tag_profiles'].keys())[:3]:
            profile = result['tag_profiles'][tag_id]
            print("\n  {}:".format(tag_id))
            print("    Mean: {:.2f}, Std: {:.2f}".format(profile['mean'], profile['std']))
            print("    Min: {:.2f}, Max: {:.2f}".format(profile['min'], profile['max']))
            
    except Exception as e:
        print("[ERROR] {}".format(e))
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test())
