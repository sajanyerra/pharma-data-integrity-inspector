"""
Agent 1: Data Profiler
Analyzes 24h of tag data and builds baseline statistics.
Uses deterministic math for profiles, then LLM to interpret quality signals.
"""

import numpy as np
from typing import Dict, Any, List
from datetime import datetime, timedelta
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from .base import BaseAgent
from config import settings


class DataProfiler(BaseAgent):
    """Analyzes tag data and builds baseline profiles with AI interpretation"""
    
    def __init__(self):
        super().__init__("DataProfiler")
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            temperature=0.2,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
        
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze tag data and return baseline statistics
        
        Input: {
            "hours": int (default 24),
            "tag_ids": List[str] (optional, default all tags)
        }
        
        Output: {
            "tag_profiles": Dict[tag_id, profile],
            "metadata": {...}
        }
        """
        await self.connect_db()
        
        try:
            hours = input_data.get("hours", 24)
            tag_ids = input_data.get("tag_ids", None)
            
            # Get all tags
            if tag_ids and len(tag_ids) > 0:
                placeholders = ','.join([f"'{tid}'" for tid in tag_ids])
                tags_query = f"SELECT tag_id FROM tags WHERE tag_id IN ({placeholders})"
                tags_result = await self.db_conn.fetch(tags_query)
            else:
                tags_result = await self.db_conn.fetch("SELECT tag_id FROM tags")
            
            tag_profiles = {}
            
            for tag_row in tags_result:
                tag_id = tag_row["tag_id"]
                
                # Get readings for last N hours
                cutoff_time = datetime.utcnow() - timedelta(hours=hours)
                readings = await self.db_conn.fetch(
                    "SELECT value, quality_code, timestamp FROM tag_readings WHERE tag_id = $1 AND timestamp >= $2 ORDER BY timestamp ASC LIMIT 10000",
                    tag_id, cutoff_time
                )
                
                if not readings:
                    continue
                
                # Calculate statistics
                values = [float(r["value"]) for r in readings if r["value"] is not None]
                
                if not values:
                    continue
                
                values_array = np.array(values)
                
                # Quality code distribution
                quality_codes = {}
                for r in readings:
                    qc = r["quality_code"] or "Unknown"
                    quality_codes[qc] = quality_codes.get(qc, 0) + 1
                
                # Update frequency (readings per hour)
                if len(readings) > 1:
                    time_span = (readings[0]["timestamp"] - readings[-1]["timestamp"]).total_seconds() / 3600
                    update_freq = len(readings) / max(time_span, 0.001)
                else:
                    update_freq = 0
                
                tag_profiles[tag_id] = {
                    "count": len(values),
                    "min": float(np.min(values_array)),
                    "max": float(np.max(values_array)),
                    "mean": float(np.mean(values_array)),
                    "std": float(np.std(values_array)),
                    "median": float(np.median(values_array)),
                    "q1": float(np.percentile(values_array, 25)),
                    "q3": float(np.percentile(values_array, 75)),
                    "quality_codes": quality_codes,
                    "update_frequency_per_hour": round(update_freq, 2),
                    "data_completeness": round(len(values) / (hours * 3600 / 5) * 100, 2)  # Expected readings based on 5-sec scan
                }
            
            result = {
                "tag_profiles": tag_profiles,
                "metadata": {
                    "analysis_window_hours": hours,
                    "tags_analyzed": len(tag_profiles),
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            
            # LLM interpretation of profiling results
            result["ai_interpretation"] = await self._interpret_profiles(tag_profiles)
            
            await self.save_trace(input_data, result)
            return result
            
        finally:
            await self.disconnect_db()
    
    async def _interpret_profiles(self, tag_profiles: Dict) -> str:
        """Use LLM to interpret profiling results and flag data quality concerns"""
        prompt = PromptTemplate(
            template="""You are a pharma data quality engineer. Given these sensor tag statistics from a pharmaceutical plant, provide a brief (2-3 sentence) assessment of overall data quality and any concerns.

Key stats (top tags):
{profile_summary}

Focus on: data completeness, unusual variability, quality code issues. Be specific about which tags look concerning.""",
            input_variables=["profile_summary"]
        )
        
        top_tags = dict(list(tag_profiles.items())[:5])
        summary_lines = []
        for tag_id, p in top_tags.items():
            summary_lines.append(f"{tag_id}: mean={p['mean']:.1f}, std={p['std']:.1f}, completeness={p.get('data_completeness', 'N/A')}%")
        profile_summary = "\n".join(summary_lines)
        
        try:
            chain = prompt | self.llm
            response = await chain.ainvoke({"profile_summary": profile_summary})
            return response.content if hasattr(response, 'content') else str(response)
        except Exception:
            return "Profiling complete. Review tag statistics for data quality concerns."
