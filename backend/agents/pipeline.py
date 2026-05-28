"""
LangGraph Pipeline for Pharma Data Integrity Inspector
5-stage workflow: detect → investigate → HITL → hypothesize → report
Stage 1 (Detection Engine) is deterministic. Stage 2 (Investigation Agent) is ReAct with 4 tools.
Stage 3 is HITL gate. Stage 4 (Hypothesis Agent) is single LLM call. Stage 5 is Report Generator.
"""

from typing import Dict, Any, TypedDict, List
from langgraph.graph import StateGraph, END
from agents.detection_engine import DetectionEngine
from agents.investigation_agent import InvestigationAgent
from agents.hypothesis_agent import HypothesisAgent
from agents.report_generator import ReportGenerator


class PipelineState(TypedDict, total=False):
    hours: int
    tag_ids: list
    tag_profiles: Dict[str, Any]
    data_cache: Dict[str, Any]
    tag_metadata: Dict[str, Any]
    cross_sensor_groups: Dict[str, Any]
    anomalies: list
    investigation_findings: list
    approved_anomalies: list
    hypotheses: list
    reports: Dict[str, Any]
    hitl_required: bool
    current_step: str
    agent_reasoning: str


async def detect_step(state: PipelineState) -> dict:
    """Stage 1: Detection Engine — deterministic rules, no LLM"""
    engine = DetectionEngine()
    result = await engine.execute({"hours": state.get("hours", 24)})
    anomalies = result.get("anomalies", [])
    tag_profiles = result.get("tag_profiles", {})
    data_cache = result.get("data_cache", {})
    return {
        "anomalies": anomalies,
        "tag_profiles": tag_profiles,
        "data_cache": data_cache,
        "hitl_required": len(anomalies) > 0,
        "current_step": "detected",
        "agent_reasoning": result.get("agent_reasoning", ""),
    }


async def investigate_step(state: PipelineState) -> dict:
    """Stage 2: Investigation Agent — ReAct with 4 genuine tools"""
    agent = InvestigationAgent()
    tag_metadata = state.get("tag_metadata", {})
    if not tag_metadata:
        from tag_simulator import TagSimulator
        sim = TagSimulator(seed=42)
        meta_list = sim.get_tag_metadata()
        meta_map = {m["tag_id"]: m for m in meta_list}
        for tag_id, tc in sim.TAG_CONFIGS.items():
            m = meta_map.get(tag_id, {})
            tag_metadata[tag_id] = {
                "tag_id": tag_id, "tag_name": m.get("tag_name", tag_id),
                "unit_type": m.get("unit_type", "Unknown"),
                "data_type": tc.get("data_type", "Unknown"),
                "normal_min": m.get("normal_min", 0), "normal_max": m.get("normal_max", 100),
                "description": m.get("description", ""),
            }
    cross_sensor_groups = {}
    try:
        from tag_simulator import TagSimulator
        cross_sensor_groups = TagSimulator(seed=42).CROSS_SENSOR_WITNESSES
    except Exception:
        pass

    result = await agent.execute({
        "anomalies": state.get("anomalies", []),
        "tag_profiles": state.get("tag_profiles", {}),
        "tag_metadata": tag_metadata,
        "data_cache": state.get("data_cache", {}),
        "cross_sensor_groups": cross_sensor_groups,
    })
    return {
        "investigation_findings": result.get("investigation_findings", []),
        "tag_metadata": tag_metadata,
        "current_step": "investigated",
        "agent_reasoning": state.get("agent_reasoning", "") + "\n\n" + result.get("agent_reasoning", ""),
    }


async def hypothesize_step(state: PipelineState) -> dict:
    """Stage 4: Hypothesis Agent — single LLM call with investigation findings"""
    generator = HypothesisAgent()
    approved = state.get("approved_anomalies", state.get("anomalies", []))
    result = await generator.execute({
        "anomalies": approved,
        "investigation_findings": state.get("investigation_findings", []),
    })
    return {
        "hypotheses": result.get("hypotheses", []),
        "current_step": "hypothesized",
        "agent_reasoning": state.get("agent_reasoning", "") + "\n\n" + result.get("agent_reasoning", ""),
    }


async def report_step(state: PipelineState) -> dict:
    """Stage 5: Report Generator — templates + LLM narrative"""
    reporter = ReportGenerator()
    result = await reporter.execute({
        "anomalies": state.get("anomalies", []),
        "hypotheses": state.get("hypotheses", [])
    })
    return {
        "reports": result,
        "current_step": "reported"
    }


def route_after_detection(state: PipelineState) -> str:
    if state.get("hitl_required", False):
        return "investigate"
    return "end"


class PharmaPipeline:
    """LangGraph-powered 5-stage pipeline with HITL gate"""

    def __init__(self):
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(PipelineState)

        workflow.add_node("detect", detect_step)
        workflow.add_node("investigate", investigate_step)
        workflow.add_node("hitl_gate", lambda state: {"current_step": "awaiting_hitl"})
        workflow.add_node("hypothesize", hypothesize_step)
        workflow.add_node("report", report_step)

        workflow.set_entry_point("detect")
        workflow.add_conditional_edges("detect", route_after_detection, {
            "investigate": "investigate",
            "end": END
        })
        workflow.add_edge("investigate", "hitl_gate")
        workflow.add_edge("hitl_gate", "hypothesize")
        workflow.add_edge("hypothesize", "report")
        workflow.add_edge("report", END)

        return workflow.compile()

    async def run(self, initial_input: Dict[str, Any]) -> Dict[str, Any]:
        """Run detect + investigate. Hypothesize/report after HITL approval."""
        state = {
            "hours": initial_input.get("hours", 24),
            "tag_ids": initial_input.get("tag_ids", None),
            "tag_profiles": {},
            "tag_metadata": {},
            "data_cache": {},
            "cross_sensor_groups": {},
            "anomalies": [],
            "investigation_findings": [],
            "approved_anomalies": [],
            "hypotheses": [],
            "reports": {},
            "hitl_required": False,
            "current_step": "init",
            "agent_reasoning": "",
        }

        detect_result = await detect_step(state)
        state.update(detect_result)
        print(f"[Pipeline] Detection Engine done: {len(state.get('anomalies', []))} anomalies")

        if state.get("hitl_required"):
            inv_result = await investigate_step(state)
            state.update(inv_result)
            print(f"[Pipeline] Investigation Agent done: {len(state.get('investigation_findings', []))} findings")

        return {
            "tag_profiles": state.get("tag_profiles", {}),
            "anomalies": state["anomalies"],
            "investigation_findings": state.get("investigation_findings", []),
            "hitl_required": state["hitl_required"],
            "current_step": state["current_step"],
            "agent_reasoning": state.get("agent_reasoning", ""),
            "message": f"Pipeline: {len(state['anomalies'])} anomalies detected and investigated. Awaiting HITL review."
        }