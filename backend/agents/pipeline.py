"""
LangGraph Pipeline for Pharma Data Integrity Inspector
Orchestrates the 3-stage workflow with HITL routing.
Agent 1 (Detection) is a ReAct agent with tools. Agent 2 (Hypothesis) is a ReAct agent with tools.
"""

from typing import Dict, Any, TypedDict, List
from langgraph.graph import StateGraph, END
from agents.detection_agent import DetectionAgent
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
    agent_reasoning: str


async def detect_step(state: PipelineState) -> dict:
    """Stage 1: Detection Agent — baseline rules + ReAct investigation"""
    detector = DetectionAgent()
    result = await detector.execute({
        "hours": state.get("hours", 24),
    })
    anomalies = result.get("anomalies", [])
    tag_profiles = result.get("tag_profiles", {})
    return {
        "anomalies": anomalies,
        "tag_profiles": tag_profiles,
        "hitl_required": len(anomalies) > 0,
        "current_step": "detected",
        "agent_reasoning": result.get("agent_reasoning", ""),
    }


async def hypothesize_step(state: PipelineState) -> dict:
    """Stage 2: Hypothesis Agent — ReAct investigation + root cause generation"""
    generator = HypothesisGenerator()
    approved = state.get("approved_anomalies", state.get("anomalies", []))
    result = await generator.execute({
        "anomalies": approved
    })
    return {
        "hypotheses": result.get("hypotheses", []),
        "current_step": "hypothesized",
        "agent_reasoning": state.get("agent_reasoning", "") + "\n\n" + result.get("agent_reasoning", ""),
    }


async def report_step(state: PipelineState) -> dict:
    """Stage 3: Report Generator — templates + LLM narrative"""
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
        return "hitl_gate"
    return "end"


class PharmaPipeline:
    """LangGraph-powered pipeline with HITL gate"""

    def __init__(self):
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(PipelineState)

        workflow.add_node("detect", detect_step)
        workflow.add_node("hitl_gate", lambda state: {"current_step": "awaiting_hitl"})
        workflow.add_node("hypothesize", hypothesize_step)
        workflow.add_node("report", report_step)

        workflow.set_entry_point("detect")
        workflow.add_conditional_edges("detect", route_after_detection, {
            "hitl_gate": "hitl_gate",
            "end": END
        })
        workflow.add_edge("hitl_gate", "hypothesize")
        workflow.add_edge("hypothesize", "report")
        workflow.add_edge("report", END)

        return workflow.compile()

    async def run(self, initial_input: Dict[str, Any]) -> Dict[str, Any]:
        """Run detect only. Hypothesize/report after HITL approval."""
        state = {
            "hours": initial_input.get("hours", 24),
            "tag_ids": initial_input.get("tag_ids", None),
            "tag_profiles": {},
            "anomalies": [],
            "approved_anomalies": [],
            "hypotheses": [],
            "reports": {},
            "hitl_required": False,
            "current_step": "init",
            "agent_reasoning": "",
        }

        detect_result = await detect_step(state)
        state.update(detect_result)
        print(f"[Pipeline] Detection Agent done: {len(state.get('anomalies', []))} anomalies")

        return {
            "tag_profiles": state.get("tag_profiles", {}),
            "anomalies": state["anomalies"],
            "hitl_required": state["hitl_required"],
            "current_step": state["current_step"],
            "agent_reasoning": state.get("agent_reasoning", ""),
            "message": f"Pipeline: {len(state['anomalies'])} anomalies detected. Awaiting HITL review."
        }