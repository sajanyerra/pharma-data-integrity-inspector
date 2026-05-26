import asyncio
import sys
sys.path.insert(0, '.')

async def generate_reports():
    print("=" * 60)
    print("GENERATING REPORTS (Agent 4)")
    print("=" * 60)
    
    from database import async_session_maker
    from sqlalchemy import text
    from agents.report_generator import ReportGenerator
    
    # Get anomalies with hypotheses
    async with async_session_maker() as session:
        result = await session.execute(text("""
            SELECT a.*, t.tag_name 
            FROM anomalies a 
            JOIN tags t ON a.tag_id = t.tag_id 
            WHERE a.hypothesis IS NOT NULL
        """))
        rows = result.fetchall()
        
    if not rows:
        print("\nNo anomalies with hypotheses found!")
        return
    
    anomalies = []
    for row in rows:
        anomalies.append({
            'id': row.id, 'tag_id': row.tag_id, 'tag_name': row.tag_name,
            'anomaly_type': row.anomaly_type, 'confidence': float(row.confidence) if row.confidence else 0.0,
            'evidence': row.evidence if isinstance(row.evidence, dict) else {},
            'detected_at': str(row.detected_at) if row.detected_at else '',
            'hitl_status': row.hitl_status, 'hypothesis': row.hypothesis,
            'recommended_action': row.recommended_action,
            'severity': 'high' if (row.confidence and float(row.confidence) > 0.7) else 'medium'
        })
    
    print("\nFound {} anomalies with hypotheses".format(len(anomalies)))
    
    # Agent 4: Report Generator
    print("\n[Agent 4] Generating reports...")
    generator = ReportGenerator()
    
    result = await generator.execute({
        'anomalies': anomalies,
        'hypotheses': [{'tag_id': a['tag_id'], 'root_cause': a['hypothesis'], 'recommended_action': a['recommended_action'], 'confidence': a['confidence'], 'alternative_causes': [], 'pharma_impact': ''} for a in anomalies],
        'tag_profiles': {}
    })
    
    print("\n" + "=" * 60)
    print("REPORTS GENERATED SUCCESSFULLY")
    print("=" * 60)
    print("\nFiles created:")
    print("  PDF:  {}".format(result['pdf_path']))
    print("  HTML: {}".format(result['html_path']))
    print("  JSON: {}".format(result['json_path']))
    print("\nYou can now download these reports from the UI!")

if __name__ == '__main__':
    asyncio.run(generate_reports())
