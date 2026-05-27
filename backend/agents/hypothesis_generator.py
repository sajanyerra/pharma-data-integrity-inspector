"""
Agent 2: Hypothesis Generator (ReAct)
Uses LLM with tools to investigate anomalies before forming root cause hypotheses.
Applies OutputGuardrail before storing results.
"""

import json
from typing import Dict, Any, List
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langgraph.prebuilt import create_react_agent
from .base import BaseAgent
from .guardrail import guardrail
from .hypothesis_tools import set_hypothesis_context
from config import settings


class HypothesisGenerator(BaseAgent):
    """Generates root cause hypotheses using ReAct agent with investigation tools"""

    ROOT_CAUSE_KB = {
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
        "rate_of_change_violation": [
            "Process upset (valve malfunction, pump trip)",
            "Sensor response to actual rapid change (verify process)",
            "Electrical spike affecting transmitter",
            "Control system oscillation",
        ],
        "noise_burst": [
            "Electrical interference or grounding issue",
            "Sensor signal conditioning failure",
            "Loose wiring connection causing intermittent signal",
            "EMI from nearby equipment startup",
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

    RECOMMENDED_ACTIONS = {
        "sensor_drift": "Schedule sensor calibration. Review calibration history. Consider more frequent calibration interval.",
        "stuck_value": "Check sensor wiring and connections. Verify network connectivity. Replace transmitter if needed.",
        "impossible_readings": "Immediate sensor inspection required. Check wiring configuration. Verify transmitter settings.",
        "rate_of_change_violation": "Review process events at anomaly time. Check control valve positions. Verify sensor response time.",
        "noise_burst": "Inspect wiring and grounding. Check for nearby equipment causing EMI. Review signal conditioning.",
        "correlation_breakdown": "Compare both sensors to handheld meter. Identify failed sensor. Review process changes.",
        "cip_temperature_low": "Verify CIP cycle completion. Check steam supply pressure. Inspect temperature controller. Schedule heat exchanger cleaning.",
        "fda_audit_trail_concern": "Immediate compliance review required. Audit trail investigation. Review access logs. Notify quality assurance.",
        "cross_sensor_inconsistency": "Compare suspect sensor to handheld reference. Check calibration date. Inspect thermowell or sensor well. Review transmitter configuration for offset errors.",
    }

    def __init__(self):
        super().__init__("HypothesisGenerator")
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL, temperature=0.3,
            api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL,
        )

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        await self.connect_db()

        try:
            anomalies = input_data.get("anomalies", [])
            if not anomalies:
                return {"hypotheses": [], "summary": {"total": 0}, "agent_reasoning": ""}

            # Load tag metadata for all anomalies
            tag_ids = list(set(a.get("tag_id", "") for a in anomalies if a.get("tag_id")))
            tag_metadata = {}
            async with self.db_conn.transaction():
                for tid in tag_ids:
                    row = await self.db_conn.fetchrow(
                        "SELECT tag_id, tag_name, unit_type, data_type, description, normal_min, normal_max FROM tags WHERE tag_id = $1", tid)
                    if row:
                        tag_metadata[row["tag_id"]] = dict(row)

            # Set context for tools
            from .hypothesis_tools import get_tag_details, get_process_context, get_similar_anomalies
            set_hypothesis_context(anomalies, tag_metadata)

            # Run ReAct agent to investigate, then generate hypotheses
            hypotheses = []
            agent_reasoning_steps = []

            for anomaly in anomalies:
                try:
                    tag_id = anomaly.get("tag_id", "Unknown")
                    anomaly_type = anomaly.get("anomaly_type", "unknown")
                    evidence = anomaly.get("evidence", {})
                    if isinstance(evidence, str):
                        try: evidence = json.loads(evidence)
                        except: evidence = {}

                    # ── Phase 1: ReAct agent investigates ──
                    reasoning = ""
                    try:
                        react_agent = create_react_agent(
                            model=self.llm,
                            tools=[get_tag_details, get_process_context, get_similar_anomalies],
                            prompt="You are a pharma process engineer investigating sensor anomalies. "
                                   "Use the available tools to gather information about the affected sensor, "
                                   "its process context, and whether similar anomalies exist. "
                                   "Then provide your root cause analysis. "
                                   "Keep your response concise — 2-3 sentences about the likely root cause "
                                   "and what additional investigation is needed.",
                        )

                        result = await react_agent.ainvoke(
                            {"messages": [{"role": "user",
                              "content": f"Investigate this anomaly: {tag_id} has {anomaly_type.replace('_', ' ')} "
                                         f"({anomaly.get('confidence', 0):.0%} confidence). "
                                         f"Evidence: {json.dumps(evidence)[:300]}. "
                                         f"Please use the tools to check tag details, process context, and similar anomalies."}]}
                        )

                        steps = []
                        for msg in result.get("messages", []):
                            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                                for tc in msg.tool_calls:
                                    tool_name = tc.get('name', 'unknown')
                                    tool_args = tc.get('args', {})
                                    steps.append(f"Called {tool_name}({json.dumps(tool_args) if isinstance(tool_args, dict) else str(tool_args)})")
                            elif hasattr(msg, 'type') and msg.type == 'tool':
                                content = msg.content[:200] if msg.content else ""
                                steps.append(f"Result: {content}")
                            elif hasattr(msg, 'content') and msg.content and not hasattr(msg, 'tool_calls'):
                                if msg.content.strip():
                                    steps.append(f"Agent: {msg.content.strip()[:300]}")

                        reasoning = "\n".join(steps) if steps else ""
                        agent_reasoning_steps.append(f"--- {tag_id}: {anomaly_type} ---\n{reasoning}")

                    except Exception as e:
                        print(f"[HypothesisGenerator] ReAct agent failed for {tag_id}: {e}")
                        reasoning = ""

                    # ── Phase 2: Generate hypothesis from investigation ──
                    tag_info = tag_metadata.get(tag_id, {})
                    known_causes = self.ROOT_CAUSE_KB.get(anomaly_type, ["Unknown anomaly type"])
                    recommended_action = self.RECOMMENDED_ACTIONS.get(anomaly_type, "Investigate anomaly")

                    try:
                        from langchain_core.prompts import PromptTemplate
                        prompt = PromptTemplate(
                            template="""You are a pharma process engineer. Based on the investigation results, provide a root cause hypothesis.

Tag: {tag_id} ({tag_name}, {unit_type})
Anomaly: {anomaly_type}
Evidence: {evidence}
Investigation: {reasoning}
Known causes for this type: {known_causes}

Provide your analysis in this exact JSON format:
{{
  "root_cause": "Primary root cause hypothesis (1-2 sentences)",
  "confidence": 0.0-1.0,
  "recommended_action": "Specific action to resolve",
  "alternative_causes": ["Alternative cause 1", "Alternative cause 2"],
  "pharma_impact": "Impact on product quality/compliance"
}}""",
                            input_variables=["tag_id", "tag_name", "unit_type", "anomaly_type",
                                            "evidence", "reasoning", "known_causes"]
                        )

                        chain = prompt | self.llm | JsonOutputParser()
                        response = await chain.ainvoke({
                            "tag_id": tag_id,
                            "tag_name": tag_info.get("tag_name", "Unknown"),
                            "unit_type": tag_info.get("unit_type", "Unknown"),
                            "anomaly_type": anomaly_type,
                            "evidence": str(evidence)[:300],
                            "reasoning": reasoning[:500] if reasoning else "No investigation data available.",
                            "known_causes": "\n".join(f"- {c}" for c in known_causes),
                        })

                        hypothesis = {
                            "root_cause": response.get("root_cause", known_causes[0]),
                            "confidence": float(response.get("confidence", 0.5)),
                            "recommended_action": response.get("recommended_action", recommended_action),
                            "alternative_causes": response.get("alternative_causes", known_causes[1:3]),
                            "pharma_impact": response.get("pharma_impact", ""),
                        }
                    except Exception:
                        hypothesis = {
                            "root_cause": known_causes[0] if known_causes else "Unknown root cause",
                            "confidence": 0.5,
                            "recommended_action": recommended_action,
                            "alternative_causes": known_causes[1:3] if len(known_causes) > 1 else [],
                            "pharma_impact": "Review required for compliance assessment",
                        }

                    # Apply guardrail
                    hypothesis = guardrail.validate_hypothesis(hypothesis)

                    hypotheses.append({
                        "anomaly_id": anomaly.get("id"),
                        "tag_id": tag_id,
                        "anomaly_type": anomaly_type,
                        "root_cause": hypothesis["root_cause"],
                        "confidence": hypothesis["confidence"],
                        "recommended_action": hypothesis["recommended_action"],
                        "alternative_causes": hypothesis.get("alternative_causes", []),
                        "pharma_impact": hypothesis.get("pharma_impact", ""),
                        "timestamp": datetime.utcnow().isoformat()
                    })

                    # Update database
                    await self.db_conn.execute(
                        "UPDATE anomalies SET hypothesis = $1, recommended_action = $2 WHERE id = $3",
                        hypothesis["root_cause"], hypothesis["recommended_action"], anomaly.get("id")
                    )

                except Exception as e:
                    print(f"Error processing anomaly {anomaly.get('tag_id', 'unknown')}: {e}")
                    continue

            result = {
                "hypotheses": hypotheses,
                "agent_reasoning": "\n\n".join(agent_reasoning_steps),
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