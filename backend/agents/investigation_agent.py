"""
Stage 2: Investigation Agent (ReAct)
Receives anomalies from the Detection Engine, investigates each one using 4 genuine tools
that query simulated external systems (historian, MES, CMMS, LIMS).
The LLM decides which tools to call based on the anomaly type — different anomalies
lead to different investigation paths. That's genuine agency.
"""

import json
from typing import Dict, Any, List
from datetime import datetime
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from .base import BaseAgent
from .investigation_tools import set_investigation_context
from .investigation_tools import query_historian, query_events, query_maintenance, query_lab_results
from .guardrail import guardrail
from config import settings


class InvestigationAgent(BaseAgent):
    """Investigates anomalies using ReAct agent with 4 external-system tools"""

    ANOMALY_GUIDANCE = {
        "sensor_drift": "Drift suggests gradual calibration degradation. Check the historian for a long-term trend (48h), then check if there was a grade change or batch start, then check maintenance history for recent calibration.",
        "stuck_value": "Stuck value usually means a communication failure. Check the historian for the stuck window (6h), then check DCS diagnostics via maintenance history, then check if there was recent maintenance on this loop.",
        "noise_burst": "Noise bursts often come from electrical interference. Check the historian at high resolution (1h, 1min), then check if there was an equipment startup nearby. Maintenance is unlikely to help here.",
        "rate_of_change_violation": "Rapid changes suggest a process upset or equipment issue. Check the historian (1-6h), then check for process upsets or equipment startups. Maintenance might be relevant if a valve or controller failed.",
        "correlation_breakdown": "A breakdown in correlation suggests one sensor changed behavior. Check the historian for both tags (24h), then check for grade changes that might explain a process shift.",
        "cross_sensor_inconsistency": "This is a Silent Lie — the sensor reads plausibly but contradicts its witnesses. Check the historian for the suspect tag AND its witnesses, then check lab results to see if product quality was affected.",
        "cip_temperature_low": "CIP temperature below sterilization threshold. Check the historian for the CIP loop, then check maintenance on the steam heater or temperature controller.",
        "fda_audit_trail_concern": "Audit trail concerns are about compliance, not process. Check maintenance for any system changes, then check lab results for any concurrent product impact.",
        "impossible_readings": "Impossible readings mean the sensor is clearly broken. Check the historian to see when it started, then check maintenance for recent repair/recalibration.",
    }

    def __init__(self):
        super().__init__("InvestigationAgent")
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL, temperature=0.1,
            api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL,
        )
        self.tools = [query_historian, query_events, query_maintenance, query_lab_results]

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        await self.connect_db()
        try:
            anomalies = input_data.get("anomalies", [])
            tag_profiles = input_data.get("tag_profiles", {})
            tag_metadata = input_data.get("tag_metadata", {})
            data_cache = input_data.get("data_cache", {})
            cross_sensor_groups = input_data.get("cross_sensor_groups", {})

            if not anomalies:
                return {"investigation_findings": [], "agent_reasoning": "", "summary": {"total_investigated": 0}}

            from tag_simulator import TagSimulator
            sim = TagSimulator(seed=42)

            set_investigation_context(
                anomalies=anomalies,
                tag_metadata=tag_metadata,
                data_cache=data_cache,
                tag_profiles=tag_profiles,
                cross_sensor_groups=cross_sensor_groups,
                simulator=sim,
            )

            findings = []
            all_reasoning = []

            react_agent = create_react_agent(
                model=self.llm,
                tools=self.tools,
                prompt="You are a pharma process engineer investigating sensor anomalies in a manufacturing plant. "
                       "You have access to 4 tools that query external systems: the PI Historian (time series data), "
                       "the MES (process events like grade changes and batch starts), the CMMS (maintenance history), "
                       "and LIMS (lab quality results). "
                       "Investigate each anomaly by calling the RIGHT tools for that anomaly type. "
                       "Different anomalies need different investigation paths: "
                       "- Drift: historian (long window) → events (grade change?) → maintenance (calibration?) "
                       "- Stuck value: historian (short window) → maintenance (wiring/comm?) "
                       "- Noise burst: historian (high-res) → events (equipment startup?) "
                       "- Cross-sensor inconsistency: historian (both tags) → lab results (product impact?) "
                       "Do NOT call all tools on every anomaly — only the relevant ones. "
                       "After your investigation, provide a concise 2-3 sentence summary of your findings.",
            )

            for anomaly in anomalies:
                tag_id = anomaly.get("tag_id", "Unknown")
                anomaly_type = anomaly.get("anomaly_type", "unknown")
                confidence = anomaly.get("confidence", 0)
                evidence = anomaly.get("evidence", {})
                if isinstance(evidence, str):
                    try:
                        evidence = json.loads(evidence)
                    except Exception:
                        evidence = {}

                guidance = self.ANOMALY_GUIDANCE.get(anomaly_type, "Investigate this anomaly using the appropriate tools.")

                user_msg = (
                    f"Investigate anomaly on {tag_id}: {anomaly_type.replace('_', ' ')} "
                    f"(confidence: {confidence:.0%}).\n"
                    f"Evidence: {json.dumps(evidence, default=str)[:300]}\n\n"
                    f"Investigation guidance: {guidance}\n\n"
                    f"Use the tools to investigate. Only call tools that are relevant to this anomaly type."
                )

                steps = []
                try:
                    result = await react_agent.ainvoke(
                        {"messages": [{"role": "user", "content": user_msg}]},
                    )
                    for msg in result.get("messages", []):
                        if hasattr(msg, 'tool_calls') and msg.tool_calls:
                            for tc in msg.tool_calls:
                                tool_name = tc.get('name', 'unknown')
                                tool_args = tc.get('args', {})
                                steps.append(f"Called {tool_name}({json.dumps(tool_args) if isinstance(tool_args, dict) else tool_args})")
                        elif hasattr(msg, 'type') and msg.type == 'tool':
                            content = msg.content[:150] if msg.content else ""
                            steps.append(f"Result: {content}")
                        elif hasattr(msg, 'content') and msg.content and not hasattr(msg, 'tool_calls'):
                            if msg.content.strip():
                                steps.append(f"Agent: {msg.content.strip()[:200]}")
                except Exception as e:
                    print(f"[InvestigationAgent] ReAct failed for {tag_id}: {e}")
                    steps.append(f"Investigation failed: {str(e)[:100]}")

                agent_text = ""
                for s in steps:
                    if s.startswith("Agent: "):
                        agent_text = s[7:]
                        break

                reasoning_text = "\n".join(steps) if steps else ""

                finding = guardrail.sanitize_text(f"Investigation of {tag_id} ({anomaly_type}): {agent_text}") if agent_text else f"No investigation result for {tag_id}"
                findings.append({
                    "tag_id": tag_id,
                    "anomaly_type": anomaly_type,
                    "investigation_summary": finding,
                    "tools_called": [s for s in steps if s.startswith("Called ")],
                })
                all_reasoning.append(f"--- {tag_id}: {anomaly_type} ---\n{reasoning_text}")

            combined_reasoning = "\n\n".join(all_reasoning)

            result = {
                "investigation_findings": findings,
                "agent_reasoning": combined_reasoning,
                "summary": {"total_investigated": len(findings)},
            }

            await self.save_trace(input_data, result)
            return result

        finally:
            await self.disconnect_db()