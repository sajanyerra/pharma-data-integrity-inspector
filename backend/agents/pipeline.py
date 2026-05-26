"""
LangGraph Multi-Agent Pipeline for Pharma Data Integrity Inspector
Orchestrates the 4-agent workflow as a StateGraph with conditional HITL routing.
"""

from typing import Dict, Any, TypedDict, Annotated
from langgraph.graph import StateGraph, END
from agents.data_profiler import DataProfiler
from agents.anomaly_detector import AnomalyDetector
from agents.hypothesis_generator import HypothesisGenerator
from agents.report_generator import ReportGenerator


class PipelineState(TypedDict, total=False):
    hours: int
    tag_ids: list
    tag_profiles: Dict[str, Any]
    anomalies: list
    approved_anomalies: list
    hypotheses: list
    reports: Dict[str, Any]
    hitl_required: bool
    current_step: str


async def profile_step(state: PipelineState) -> dict:
    """Agent 1: Data Profiler"""
    profiler = DataProfiler()
    result = await profiler.execute({
        "hours": state.get("hours", 24),
        "tag_ids": state.get("tag_ids", None)
    })
    return {"tag_profiles": result["tag_profiles"], "current_step": "profiled"}


async def detect_step(state: PipelineState) -> dict:
    """Agent 2: Anomaly Detector"""
    detector = AnomalyDetector()
    result = await detector.execute({
        "tag_profiles": state["tag_profiles"],
        "hours": state.get("hours", 24)
    })
    anomalies = result.get("anomalies", [])
    return {
        "anomalies": anomalies,
        "hitl_required": len(anomalies) > 0,
        "current_step": "detected"
    }


async def hypothesize_step(state: PipelineState) -> dict:
    """Agent 3: Hypothesis Generator"""
    generator = HypothesisGenerator()
    approved = state.get("approved_anomalies", state.get("anomalies", []))
    result = await generator.execute({
        "anomalies": approved
    })
    return {
        "hypotheses": result.get("hypotheses", []),
        "current_step": "hypothesized"
    }


async def report_step(state: PipelineState) -> dict:
    """Agent 4: Report Generator"""
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
    """Conditional edge: if anomalies found, require HITL; otherwise skip to end"""
    if state.get("hitl_required", False):
        return "hitl_gate"
    return "end"


class PharmaPipeline:
    """LangGraph-powered multi-agent pipeline"""

    def __init__(self):
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(PipelineState)

        workflow.add_node("profile", profile_step)
        workflow.add_node("detect", detect_step)
        workflow.add_node("hitl_gate", lambda state: {"current_step": "awaiting_hitl"})
        workflow.add_node("hypothesize", hypothesize_step)
        workflow.add_node("report", report_step)

        workflow.set_entry_point("profile")
        workflow.add_edge("profile", "detect")
        workflow.add_conditional_edges("detect", route_after_detection, {
            "hitl_gate": "hitl_gate",
            "end": END
        })
        workflow.add_edge("hitl_gate", "hypothesize")
        workflow.add_edge("hypothesize", "report")
        workflow.add_edge("report", END)

        return workflow.compile()

    async def run(self, initial_input: Dict[str, Any]) -> Dict[str, Any]:
        """Run the full pipeline. For HITL, this runs profile+detect only.
        Hypothesize/report run after human approval."""
        state = {
            "hours": initial_input.get("hours", 24),
            "tag_ids": initial_input.get("tag_ids", None),
            "tag_profiles": {},
            "anomalies": [],
            "approved_anomalies": [],
            "hypotheses": [],
            "reports": {},
            "hitl_required": False,
            "current_step": "init"
        }

        profile_result = await profile_step(state)
        state.update(profile_result)

        detect_result = await detect_step(state)
        state.update(detect_result)

        return {
            "tag_profiles": state["tag_profiles"],
            "anomalies": state["anomalies"],
            "hitl_required": state["hitl_required"],
            "current_step": state["current_step"],
            "message": f"Pipeline: {len(state['anomalies'])} anomalies detected. Awaiting HITL review."
        }