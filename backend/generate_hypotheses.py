import asyncio
import sys
sys.path.insert(0, '.')

async def generate():
    print("=" * 60)
    print("GENERATING ROOT CAUSE HYPOTHESES (Agent 3)")
    print("=" * 60)
    
    from database import async_session_maker
    from sqlalchemy import text
    from agents.hypothesis_generator import HypothesisGenerator
    
    # Get pending anomalies
    async with async_session_maker() as session:
        result = await session.execute(text("SELECT id, tag_id, anomaly_type, confidence, evidence FROM anomalies WHERE hitl_status = 'pending' LIMIT 5"))
        anomalies = [dict(zip(['id', 'tag_id', 'anomaly_type', 'confidence', 'evidence'], row)) for row in result.fetchall()]
    
    if not anomalies:
        print("\nNo pending anomalies found. Approve some in HITL first!")
        return
    
    print("\nFound {} pending anomalies".format(len(anomalies)))
    for a in anomalies:
        print("  - {}: {}".format(a['tag_id'], a['anomaly_type']))
    
    # Agent 3: Hypothesis Generator
    print("\n[Agent 3] Generating hypotheses...")
    generator = HypothesisGenerator()
    await generator.connect_db()
    
    try:
        for anomaly in anomalies:
            print("\n  Analyzing {}...".format(anomaly['tag_id']))
            
            # Get tag metadata
            async with async_session_maker() as session:
                result = await session.execute(text("SELECT tag_name, unit_type, description FROM tags WHERE tag_id = :tag_id"), {"tag_id": anomaly['tag_id']})
                tag_info = result.fetchone()
            
            if not tag_info:
                print("    [SKIP] Tag not found")
                continue
            
            # Generate hypothesis
            hypothesis = await generator._generate_hypothesis_llm(
                tag_id=anomaly['tag_id'],
                tag_name=tag_info[0],
                unit_type=tag_info[1],
                anomaly_type=anomaly['anomaly_type'],
                evidence=anomaly['evidence'] if isinstance(anomaly['evidence'], dict) else {},
                description=tag_info[2] or ""
            )
            
            print("    [OK] Root cause: {}".format(hypothesis['root_cause'][:80]))
            print("    Confidence: {:.0f}%".format(hypothesis['confidence'] * 100))
            print("    Action: {}".format(hypothesis['recommended_action'][:60]))
            
            # Save to database
            async with async_session_maker() as session:
                await session.execute(text("""
                    UPDATE anomalies 
                    SET hitl_status = 'approved', hypothesis = :hypothesis, recommended_action = :action
                    WHERE id = :id
                """), {
                    "id": anomaly['id'],
                    "hypothesis": hypothesis['root_cause'],
                    "action": hypothesis['recommended_action']
                })
                await session.commit()
        
        print("\n" + "=" * 60)
        print("HYPOTHESES GENERATED SUCCESSFULLY")
        print("=" * 60)
        
    finally:
        await generator.disconnect_db()

if __name__ == '__main__':
    asyncio.run(generate())
