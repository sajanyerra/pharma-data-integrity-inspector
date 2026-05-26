"""
Agent 3: Hypothesis Generator
Generates root cause hypotheses for selected anomalies
"""

from typing import Dict, Any, List
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from .base import BaseAgent
from .guardrail import guardrail
from config import settings


class HypothesisGenerator(BaseAgent):
    """Generates root cause hypotheses with pharma context"""
    
    def __init__(self):
        super().__init__("HypothesisGenerator")
        
        # Initialize LLM with OpenAI
        self.llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0.3,
            openai_api_key=settings.OPENAI_API_KEY
        )
        
        # Root cause knowledge base
        self.root_cause_knowledge = {
            "sensor_drift": [
                "Sensor calibration drift due to coating buildup",
                "Aging sensor element requiring replacement",
                "Temperature cycling causing sensor degradation",
                "Process fluid contamination on sensor probe",
            ],
            "stuck_value": [
                "Sensor communication failure (cable/wiring issue)",
                "Frozen transmitter (electronics failure)",
                "Network connectivity loss to historian",
                "Sensor power supply failure",
            ],
            "impossible_readings": [
                "Sensor wiring fault (short/open circuit)",
                "Transmitter configuration error",
                "Electrical noise interference",
                "ADC (analog-to-digital converter) failure",
            ],
            "quality_code_mismatch": [
                "Manual override without proper justification",
                "Operator bypassing quality checks",
                "SCADA system quality code mapping error",
                "Training gap - operator not following procedures",
            ],
            "rate_of_change_violation": [
                "Process upset (valve malfunction, pump trip)",
                "Sensor response to actual rapid change (verify process)",
                "Electrical spike affecting transmitter",
                "Control system oscillation",
            ],
            "data_gaps": [
                "Network infrastructure issue",
                "Historian server overload",
                "PLC communication timeout",
                "Scheduled maintenance not logged",
            ],
            "statistical_outliers": [
                "Intermittent sensor malfunction",
                "Process transients not captured in normal operation",
                "Sampling/scan rate mismatch",
                "Data corruption during transmission",
            ],
            "correlation_breakdown": [
                "One sensor in pair has failed (identify which)",
                "Process change affecting relationship",
                "Control strategy change not documented",
                "Equipment degradation (fouling, wear)",
            ],
            "cip_temperature_low": [
                "Steam supply issue to CIP heater",
                "Temperature controller malfunction",
                "CIP cycle not completed (operator intervention)",
                "Heat exchanger fouling reducing heat transfer",
            ],
            "fda_audit_trail_concern": [
                "Electronic records compliance violation",
                "Audit trail system malfunction",
                "Unauthorized data modification",
                "System clock synchronization issue",
            ],
            "cross_sensor_inconsistency": [
                "Sensor miscalibration — sensor reads within range but contradicts correlated witnesses",
                "Transmitter offset error — calibration drifted without triggering threshold alerts",
                "Thermowell fouling or insulation degradation causing local reading offset",
                "Signal conditioning error in DCS/PLC analog input card",
            ],
        }
        
        self.recommended_actions = {
            "sensor_drift": "Schedule sensor calibration. Review calibration history. Consider more frequent calibration interval.",
            "stuck_value": "Check sensor wiring and connections. Verify network connectivity. Replace transmitter if needed.",
            "impossible_readings": "Immediate sensor inspection required. Check wiring configuration. Verify transmitter settings.",
            "quality_code_mismatch": "Review operator logs. Verify SCADA quality mapping. Conduct operator training refresher.",
            "rate_of_change_violation": "Review process events at anomaly time. Check control valve positions. Verify sensor response time.",
            "data_gaps": "Check network infrastructure logs. Review historian server performance. Verify PLC communication status.",
            "statistical_outliers": "Analyze outlier timestamps for patterns. Check for intermittent electrical issues. Review maintenance logs.",
            "correlation_breakdown": "Compare both sensors to handheld meter. Identify failed sensor. Review process changes.",
            "cip_temperature_low": "Verify CIP cycle completion. Check steam supply pressure. Inspect temperature controller. Schedule heat exchanger cleaning.",
            "fda_audit_trail_concern": "Immediate compliance review required. Audit trail investigation. Review access logs. Notify quality assurance.",
            "cross_sensor_inconsistency": "Compare suspect sensor to handheld reference. Check calibration date. Inspect thermowell or sensor well. Review transmitter configuration for offset errors.",
        }
        
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate hypotheses for user-selected anomalies
        
        Input: {
            "anomalies": List[anomaly_dict],
            "user_selections": List[anomaly_id] (optional)
        }
        
        Output: {
            "hypotheses": List[hypothesis_dict],
            "summary": {...}
        }
        """
        await self.connect_db()
        
        try:
            anomalies = input_data.get("anomalies", [])
            
            if not anomalies:
                return {"hypotheses": [], "summary": {"total": 0}}
            
            hypotheses = []
            
            for anomaly in anomalies:
                try:
                    tag_id = anomaly.get("tag_id", "Unknown")
                    anomaly_type = anomaly.get("anomaly_type", "unknown")
                    evidence = anomaly.get("evidence", {})
                    
                    # Ensure evidence is a dict, not a string
                    if isinstance(evidence, str):
                        import json
                        try:
                            evidence = json.loads(evidence)
                        except:
                            evidence = {}
                    
                    # Get tag metadata
                    tag_info = await self.db_conn.fetchrow(
                        "SELECT tag_name, unit_type, description FROM tags WHERE tag_id = $1",
                        tag_id
                    )
                    
                    if not tag_info:
                        print(f"Warning: Tag {tag_id} not found, skipping")
                        continue
                    
                    # Generate hypothesis using LLM
                    raw_hypothesis = await self._generate_hypothesis_llm(
                        tag_id=tag_id,
                        tag_name=tag_info["tag_name"],
                        unit_type=tag_info["unit_type"],
                        anomaly_type=anomaly_type,
                        evidence=evidence if isinstance(evidence, dict) else {},
                        description=tag_info["description"] or ""
                    )
                    
                    hypothesis = guardrail.validate_hypothesis(raw_hypothesis)
                    
                    hypotheses.append({
                        "anomaly_id": anomaly.get("id"),
                        "tag_id": tag_id,
                        "anomaly_type": anomaly_type,
                        "root_cause": hypothesis["root_cause"],
                        "confidence": hypothesis["confidence"],
                        "recommended_action": hypothesis["recommended_action"],
                        "alternative_causes": hypothesis["alternative_causes"],
                        "pharma_impact": hypothesis.get("pharma_impact", ""),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
                    # Update database with hypothesis
                    await self.db_conn.execute(
                        """
                        UPDATE anomalies
                        SET hypothesis = $1, recommended_action = $2
                        WHERE id = $3
                        """,
                        hypothesis["root_cause"],
                        hypothesis["recommended_action"],
                        anomaly.get("id")
                    )
                except Exception as e:
                    print(f"Error processing anomaly {anomaly.get('tag_id', 'unknown')}: {e}")
                    continue
            
            result = {
                "hypotheses": hypotheses,
                "summary": {
                    "total_hypotheses": len(hypotheses),
                    "high_confidence": sum(1 for h in hypotheses if h["confidence"] > 0.7),
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            
            await self.save_trace(input_data, result)
            return result
            
        finally:
            await self.disconnect_db()
    
    async def _generate_hypothesis_llm(
        self,
        tag_id: str,
        tag_name: str,
        unit_type: str,
        anomaly_type: str,
        evidence: Dict,
        description: str
    ) -> Dict[str, Any]:
        """Use LLM to generate root cause hypothesis"""
        
        prompt = PromptTemplate(
            template="""You are a pharma process engineer with 20 years of experience in pharmaceutical manufacturing, process automation, and data integrity.

Your task: Analyze the detected anomaly and provide the most likely root cause based on pharma manufacturing knowledge.

Consider these factors:
- Sensor failure modes (drift, stuck, electrical issues)
- Process upsets (valve malfunctions, pump trips, control issues)
- Maintenance activities (calibration, replacement, cleaning)
- Communication failures (network, PLC, historian)
- FDA 21 CFR Part 11 compliance implications

Provide your analysis in this exact JSON format:
{{
  "root_cause": "Primary root cause hypothesis (1-2 sentences)",
  "confidence": 0.0-1.0,
  "recommended_action": "Specific action to resolve (e.g., 'calibrate sensor', 'check wiring', 'review maintenance log')",
  "alternative_causes": ["Alternative cause 1", "Alternative cause 2"],
  "pharma_impact": "Impact on product quality/compliance if applicable"
}}

Tag Information:
- Tag ID: {tag_id}
- Tag Name: {tag_name}
- Unit Type: {unit_type}
- Description: {description}

Anomaly Detected:
- Type: {anomaly_type}
- Evidence: {evidence}

Known root causes for this anomaly type:
{known_causes}

Recommended action template:
{recommended_action}

Provide your root cause analysis in the specified JSON format.""",
            input_variables=["tag_id", "tag_name", "unit_type", "description", "anomaly_type", "evidence", "known_causes", "recommended_action"]
        )
        
        known_causes = self.root_cause_knowledge.get(anomaly_type, ["Unknown anomaly type"])
        recommended_action = self.recommended_actions.get(anomaly_type, "Investigate anomaly")
        
        try:
            chain = prompt | self.llm | JsonOutputParser()
            
            response = await chain.ainvoke({
                "tag_id": tag_id,
                "tag_name": tag_name,
                "unit_type": unit_type,
                "description": description,
                "anomaly_type": anomaly_type,
                "evidence": str(evidence),
                "known_causes": "\n".join(f"- {c}" for c in known_causes),
                "recommended_action": recommended_action
            })
            
            return {
                "root_cause": response.get("root_cause", "Unable to determine root cause"),
                "confidence": float(response.get("confidence", 0.5)),
                "recommended_action": response.get("recommended_action", recommended_action),
                "alternative_causes": response.get("alternative_causes", []),
                "pharma_impact": response.get("pharma_impact", "")
            }
            
        except Exception as e:
            # Fallback to rule-based hypothesis
            return {
                "root_cause": known_causes[0] if known_causes else "Unknown root cause",
                "confidence": 0.5,
                "recommended_action": recommended_action,
                "alternative_causes": known_causes[1:3] if len(known_causes) > 1 else [],
                "pharma_impact": "Review required for compliance assessment"
            }
