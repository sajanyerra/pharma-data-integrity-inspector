"""
Stream Ingest Service
Continuously reads simulated tag data and inserts to PostgreSQL
"""

import asyncio
import asyncpg
from datetime import datetime
from tag_simulator import TagSimulator
from config import settings

class StreamIngest:
    """Streams tag data to PostgreSQL every 5 seconds"""
    
    def __init__(self):
        self.simulator = TagSimulator(seed=42)
        self.conn = None
        self.running = False
        
    async def connect(self):
        """Establish database connection"""
        self.conn = await asyncpg.connect(settings.DATABASE_URL)
        print("Connected to PostgreSQL")
        
    async def disconnect(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()
            print("Disconnected from PostgreSQL")
            
    async def init_tags(self):
        """Initialize tag metadata in database"""
        metadata = self.simulator.get_tag_metadata()
        
        for tag in metadata:
            await self.conn.execute(
                """
                INSERT INTO tags (tag_id, tag_name, unit_type, data_type, normal_min, normal_max, scan_rate_sec, description)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (tag_id) DO NOTHING
                """,
                tag['tag_id'], tag['tag_name'], tag['unit_type'], 
                tag['data_type'], tag['normal_min'], tag['normal_max'],
                tag['scan_rate_sec'], tag['description']
            )
        print(f"Initialized {len(metadata)} tags")
        
    async def ingest_batch(self, readings: list):
        """Insert a batch of readings to database"""
        async with self.conn.transaction():
            for reading in readings:
                await self.conn.execute(
                    """
                    INSERT INTO tag_readings (tag_id, timestamp, value, quality_code)
                    VALUES ($1, $2, $3, $4)
                    """,
                    reading['tag_id'], 
                    reading['timestamp'], 
                    reading['value'], 
                    reading['quality_code']
                )
                
    async def run(self):
        """Main streaming loop"""
        self.running = True
        await self.connect()
        await self.init_tags()
        
        print("Starting stream ingest (5-second intervals)...")
        print("Press Ctrl+C to stop")
        
        try:
            while self.running:
                timestamp = datetime.utcnow()
                readings = self.simulator.generate_all_tags(timestamp)
                
                await self.ingest_batch(readings)
                
                anomaly_count = sum(1 for r in readings if r.get('is_anomaly'))
                if anomaly_count > 0:
                    print(f"[{timestamp}] Ingested {len(readings)} readings ({anomaly_count} anomalies)")
                else:
                    print(f"[{timestamp}] Ingested {len(readings)} readings")
                
                await asyncio.sleep(5)
                
        except KeyboardInterrupt:
            print("\nStopping stream ingest...")
        finally:
            self.running = False
            await self.disconnect()
            
    def stop(self):
        """Stop the streaming loop"""
        self.running = False


async def main():
    """Entry point for stream ingest service"""
    ingest = StreamIngest()
    await ingest.run()


if __name__ == '__main__':
    asyncio.run(main())
