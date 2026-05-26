"""
Seed database with 24 hours of historical tag data including injected anomalies
"""
import asyncio
import sys
sys.path.insert(0, '.')

from datetime import datetime, timedelta
from tag_simulator import TagSimulator
from database import async_session_maker
from sqlalchemy import text

async def seed_data():
    print("=" * 60)
    print("SEEDING 24 HOURS OF HISTORICAL DATA")
    print("=" * 60)
    
    simulator = TagSimulator(seed=42)
    
    # Clear existing data
    async with async_session_maker() as session:
        await session.execute(text("DELETE FROM tag_readings"))
        await session.execute(text("DELETE FROM anomalies"))
        await session.commit()
    
    print("Cleared existing data")
    
    # Generate 24 hours of data (5-second intervals = 17,280 readings per tag)
    start_time = datetime.utcnow() - timedelta(hours=24)
    total_readings = 20 * 24 * 3600 // 5  # 20 tags * 24 hours * 720 readings/hour
    
    print(f"Generating {total_readings:,} readings (20 tags x 24 hours)...")
    
    batch_size = 500
    inserted = 0
    batch = []
    
    async with async_session_maker() as session:
        for i in range(24 * 3600 // 5):  # 24 hours of 5-second intervals
            timestamp = start_time + timedelta(seconds=i * 5)
            readings = simulator.generate_all_tags(timestamp)
            
            for reading in readings:
                batch.append({
                    'tag_id': reading['tag_id'],
                    'timestamp': reading['timestamp'],
                    'value': reading['value'],
                    'quality_code': reading['quality_code']
                })
                
                if len(batch) >= batch_size:
                    await session.execute(
                        text("""
                            INSERT INTO tag_readings (tag_id, timestamp, value, quality_code)
                            VALUES (:tag_id, :timestamp, :value, :quality_code)
                        """),
                        batch
                    )
                    await session.commit()
                    inserted += len(batch)
                    batch = []
                    
                    if inserted % 5000 == 0:
                        print(f"  Inserted {inserted:,} readings...")
        
        # Insert remaining batch
        if batch:
            await session.execute(
                text("""
                    INSERT INTO tag_readings (tag_id, timestamp, value, quality_code)
                    VALUES (:tag_id, :timestamp, :value, :quality_code)
                """),
                batch
            )
            await session.commit()
            inserted += len(batch)
    
    print(f"\n[OK] Inserted {inserted:,} readings")
    
    # Verify data
    async with async_session_maker() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM tag_readings"))
        count = result.scalar()
        print(f"Total readings in database: {count:,}")
        
        result = await session.execute(text("SELECT tag_id, COUNT(*) as cnt, MIN(timestamp) as min_ts, MAX(timestamp) as max_ts FROM tag_readings GROUP BY tag_id ORDER BY tag_id LIMIT 5"))
        print("\nSample tags:")
        for row in result.fetchall():
            print(f"  {row[0]}: {row[1]} readings ({row[2]} to {row[3]})")
    
    print("\n" + "=" * 60)
    print("DATA SEEDING COMPLETE")
    print("=" * 60)
    print("\nYou can now run analysis and it should detect:")
    print("  - TI-101: Sensor drift (+2.5 C/hour for 18 hours)")
    print("  - VI-301: Stuck value (frozen at 4.2 mm/s for 6 hours)")

if __name__ == '__main__':
    asyncio.run(seed_data())
