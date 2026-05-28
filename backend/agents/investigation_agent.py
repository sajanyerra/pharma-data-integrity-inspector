"""
Stage 2: Investigation Agent
Receives anomalies from the Detection Engine, investigates each one using 4 genuine tools
that query simulated external systems (Historian, MES, CMMS, LIMS).
Tools are selected per anomaly type (ANOMALY_GUIDANCE specifies which are relevant),
executed directly, then a single LLM call summarizes the findings.
"""

import json
from typing import Dict, Any, List
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from .base import BaseAgent
from .investigation_tools import (
    set_investigation_context,
    query_historian, query_events, query_maintenance, query_lab_results,
    _historian_api, _mes_api, _cmms_api, _lims_api,
)
from .guardrail import guardrail
from config import settings


class InvestigationAgent(BaseAgent):
    """Investigates anomalies using curated tool calls + LLM summary"""

    ANOMALY_TOOL_MAP = {
        "sensor_drift": [
            {"tool": "query_historian", "args": {"hours": 48, "resolution_min": 15}},
            {"tool": "query_events", "args": {"event_type": "grade_change"}},
            {"tool": "query_maintenance", "args": {}},
        ],
        "stuck_value": [
            {"tool": "query_historian", "args": {"hours": 6, "resolution_min": 5}},
            {"tool": "query_maintenance", "args": {}},
        ],
        "noise_burst": [
            {"tool": "query_historian", "args": {"hours": 1, "resolution_min": 1}},
            {"tool": "query_events", "args": {"event_type": "equipment_startup"}},
        ],
        "rate_of_change_violation": [
            {"tool": "query_historian", "args": {"hours": 6, "resolution_min": 5}},
            {"tool": "query_events", "args": {"event_type": "process_upset"}},
            {"tool": "query_maintenance", "args": {}},
        ],
        "correlation_breakdown": [
            {"tool": "query_historian", "args": {"hours": 24, "resolution_min": 5}},
            {"tool": "query_events", "args": {"event_type": "grade_change"}},
        ],
        "cross_sensor_inconsistency": [
            {"tool": "query_historian", "args": {"hours": 24, "resolution_min": 5}},
            {"tool": "query_lab_results", "args": {"param": "assay"}},
        ],
        "cip_temperature_low": [
            {"tool": "query_historian", "args": {"hours": 6, "resolution_min": 5}},
            {"tool": "query_maintenance", "args": {}},
        ],
        "fda_audit_trail_concern": [
            {"tool": "query_maintenance", "args": {}},
            {"tool": "query_lab_results", "args": {"param": "assay"}},
        ],
        "impossible_readings": [
            {"tool": "query_historian", "args": {"hours": 6, "resolution_min": 5}},
            {"tool": "query_maintenance", "args": {}},
        ],
    }

    TOOL_EXECUTORS = {
        "query_historian": _historian_api,
        "query_events": _mes_api,
        "query_maintenance": _cmms_api,
        "query_lab_results": _lims_api,
    }

    GUIDANCE = {
        "sensor_drift": "Drift suggests gradual calibration degradation. Checked historian for long-term trend, looked for grade changes that might explain it, and checked maintenance history for recent calibration.",
        "stuck_value": "Stuck value usually means a communication failure. Checked historian for the stuck window and maintenance history for any recent work on this loop.",
        "noise_burst": "Noise bursts often come from electrical interference. Checked historian at high resolution and looked for nearby equipment startups.",
        "rate_of_change_violation": "Rapid changes suggest a process upset. Checked historian for the event window, looked for process upsets, and checked maintenance for valve/controller issues.",
        "correlation_breakdown": "One sensor changed behavior. Checked historian for both tags and looked for grade changes that might explain a process shift.",
        "cross_sensor_inconsistency": "Silent Lie — the sensor reads plausibly but contradicts its witnesses. Checked historian for both suspect and witness tags, then checked lab results for product impact.",
        "cip_temperature_low": "CIP temperature below sterilization threshold. Checked historian for the CIP loop and maintenance on the steam heater.",
        "fda_audit_trail_concern": "Audit trail concerns are about compliance, not process. Checked maintenance for system changes and lab results for concurrent product impact.",
        "impossible_readings": "Impossible readings mean the sensor is clearly broken. Checked historian for when it started and maintenance for recent repair/recalibration.",
    }

    def __init__(self):
        super().__init__("InvestigationAgent")
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL, temperature=0.1,
            api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL,
        )

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

            all_tool_results = []
            all_reasoning = []

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

                tool_plan = self.ANOMALY_TOOL_MAP.get(anomaly_type, [
                    {"tool": "query_historian", "args": {"hours": 24, "resolution_min": 15}}
                ])
                guidance = self.GUIDANCE.get(anomaly_type, "Investigated this anomaly using available tools.")

                anomaly_results = []
                steps = [f"--- {tag_id}: {anomaly_type} (confidence: {confidence:.0%}) ---"]
                steps.append(f"Guidance: {guidance}")

                for tool_spec in tool_plan:
                    tool_name = tool_spec["tool"]
                    tool_args = {"tag_id": tag_id, **tool_spec.get("args", {})}
                    executor = self.TOOL_EXECUTORS.get(tool_name)
                    if not executor:
                        continue
                    try:
                        result = executor(**tool_args)
                        result_str = json.dumps(result, default=str)[:300]
                        anomaly_results.append({"tool": tool_name, "args": tool_args, "result": result})
                        steps.append(f"Called {tool_name}({json.dumps({k: v for k, v in tool_args.items() if k != 'tag_id'})})")
                        steps.append(f"Result: {result_str[:150]}")
                    except Exception as e:
                        steps.append(f"Called {tool_name} → Error: {str(e)[:80]}")

                all_tool_results.append({
                    "tag_id": tag_id,
                    "anomaly_type": anomaly_type,
                    "evidence_summary": json.dumps(evidence, default=str)[:200],
                    "tool_results": anomaly_results,
                    "guidance": guidance,
                })
                all_reasoning.append("\n".join(steps))

            combined_tool_data = ""
            for tr in all_tool_results:
                combined_tool_data += f"\n\nAnomaly: {tr['tag_id']} ({tr['anomaly_type']})\n"
                combined_tool_data += f"Evidence: {tr['evidence_summary']}\n"
                combined_tool_data += f"Guidance: {tr['guidance']}\n"
                for r in tr.get("tool_results", []):
                    combined_tool_data += f"Tool {r['tool']}: {json.dumps(r['result'], default=str)[:250]}\n"

            prompt = ChatPromptTemplate.from_messages([
                ("system",
                 "You are a pharma process engineer. Summarize investigation findings for {count} anomalies. "
                 "For each anomaly, write 1-2 sentences about what the tool results reveal. "
                 "Be concise and specific. Do not repeat tool output verbatim."),
                ("user", "{tool_data}"),
            ])
            chain = prompt | self.llm

            try:
                llm_response = await chain.ainvoke({"count": len(all_tool_results), "tool_data": combined_tool_data})
                summary_text = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
            except Exception as e:
                print(f"[InvestigationAgent] LLM summary failed: {e}")
                summary_text = "Investigation complete. Tool results collected but LLM summary unavailable."

            summary_text = guardrail.sanitize_text(summary_text)

            per_anomaly_summaries = summary_text.split("\n")
            findings = []
            for i, tr in enumerate(all_tool_results):
                finding_text = per_anomaly_summaries[i] if i < len(per_anomaly_summaries) and per_anomaly_summaries[i].strip() else f"Investigation of {tr['tag_id']} ({tr['anomaly_type']}): tools queried, see reasoning log."
                findings.append({
                    "tag_id": tr["tag_id"],
                    "anomaly_type": tr["anomaly_type"],
                    "investigation_summary": guardrail.sanitize_text(finding_text),
                    "tools_called": [f"Called {r['tool']}" for r in tr.get("tool_results", [])],
                })

            result = {
                "investigation_findings": findings,
                "agent_reasoning": "\n\n".join(all_reasoning),
                "summary": {"total_investigated": len(findings)},
            }

            await self.save_trace(input_data, result)
            return result

        finally:
            await self.disconnect_db()