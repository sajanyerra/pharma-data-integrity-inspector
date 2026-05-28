"""
LangGraph Pipeline for Process Data Integrity Inspector
5-stage workflow: detect → investigate → HITL → hypothesize → report
Stage 1 (Detection Engine) is deterministic. Stage 2 (Investigation Agent) is ReAct with 4 tools.
Stage 3 is HITL gate (LangGraph interrupt). Stage 4 (Hypothesis Agent) is single LLM call. Stage 5 is Report Generator.
"""

from typing import Dict, Any, TypedDict, List, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
from agents.detection_engine import DetectionEngine
from agents.investigation_agent import InvestigationAgent
from agents.hypothesis_agent import HypothesisAgent
from agents.report_generator import ReportGenerator

_progress_hook = None


def set_progress_hook(hook):
    """Set a progress callback for the pipeline. Called with (event_type, data) during execution."""
    global _progress_hook
    _progress_hook = hook


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
    hitl_decisions: Optional[Dict[str, str]]


async def detect_step(state: PipelineState) -> dict:
    """Stage 1: Detection Engine — deterministic rules, no LLM"""
    if _progress_hook:
        await _progress_hook("detect_start", {"message": "Running 9 integrity checks..."})

    engine = DetectionEngine()
    result = await engine.execute({"hours": state.get("hours", 24)})
    anomalies = result.get("anomalies", [])
    tag_profiles = result.get("tag_profiles", {})
    data_cache = result.get("data_cache", {})

    if _progress_hook:
        await _progress_hook("detect_done", {"anomalies": len(anomalies)})

    return {
        "anomalies": anomalies,
        "tag_profiles": tag_profiles,
        "data_cache": data_cache,
        "hitl_required": len(anomalies) > 0,
        "current_step": "detected",
        "agent_reasoning": result.get("agent_reasoning", ""),
    }


async def investigate_step(state: PipelineState) -> dict:
    """Stage 2: Investigation Agent — ReAct with 4 genuine tools, per-anomaly progress via hook"""
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

    anomalies = state.get("anomalies", [])
    all_findings = []
    all_reasoning_parts = []

    await agent.connect_db()
    try:
        from tag_simulator import TagSimulator
        sim = TagSimulator(seed=42)
        from agents.investigation_tools import set_investigation_context
        from langgraph.prebuilt import create_react_agent

        set_investigation_context(
            anomalies=anomalies, tag_metadata=tag_metadata,
            data_cache=state.get("data_cache", {}),
            tag_profiles=state.get("tag_profiles", {}),
            cross_sensor_groups=cross_sensor_groups,
            simulator=sim,
        )

        react_agent = create_react_agent(
            model=agent.llm,
            tools=agent.tools,
            prompt="You are a pharma process engineer investigating sensor anomalies. "
                   "You have 4 tools: query_historian (PI Historian time series), "
                   "query_events (MES batch/events), query_maintenance (CMMS work orders), "
                   "query_lab_results (LIMS lab data). "
                   "Investigate by calling the RIGHT tools for each anomaly type. "
                   "Be concise — call 1-2 tools, then give a 2-3 sentence summary. "
                   "Do NOT call all tools on every anomaly.",
        )

        for i, anomaly in enumerate(anomalies):
            tag_id = anomaly.get("tag_id", "Unknown")
            anomaly_type = anomaly.get("anomaly_type", "unknown")
            if _progress_hook:
                await _progress_hook("investigate_anomaly", {
                    "tag_id": tag_id, "anomaly_type": anomaly_type,
                    "index": i, "total": len(anomalies),
                    "message": f"Stage 2: Investigating {tag_id} ({i+1}/{len(anomalies)})...",
                })

            try:
                finding = await agent._investigate_one(react_agent, anomaly)
                all_findings.append({k: v for k, v in finding.items() if k != "reasoning"})
                all_reasoning_parts.append(finding.get("reasoning", ""))
            except Exception as e:
                print(f"[Pipeline] Investigation failed for {tag_id}: {e}")
                all_reasoning_parts.append(f"--- {tag_id}: investigation failed ---\n{str(e)[:100]}")

            if _progress_hook:
                await _progress_hook("investigate_anomaly_done", {
                    "findings_so_far": all_findings,
                    "reasoning_so_far": state.get("agent_reasoning", "") + "\n\n" + "\n\n".join(all_reasoning_parts),
                })

        combined_reasoning = state.get("agent_reasoning", "") + "\n\n" + "\n\n".join(all_reasoning_parts)

        try:
            await agent.save_trace(
                {"anomalies": anomalies},
                {"investigation_findings": all_findings, "agent_reasoning": combined_reasoning, "summary": {"total_investigated": len(all_findings)}},
            )
        except Exception:
            pass

    finally:
        await agent.disconnect_db()

    return {
        "investigation_findings": all_findings,
        "tag_metadata": tag_metadata,
        "current_step": "investigated",
        "agent_reasoning": combined_reasoning,
    }


async def hitl_gate_step(state: PipelineState) -> dict:
    """Stage 3: Human-in-the-Loop Gate — LangGraph interrupt pauses execution until human provides decisions"""
    anomalies = state.get("anomalies", [])
    if not anomalies:
        return {"current_step": "hitl_skipped", "approved_anomalies": []}

    hitl_decisions = interrupt({
        "message": "Human review required: approve or reject flagged anomalies before proceeding to root cause analysis.",
        "anomalies": [
            {"tag_id": a.get("tag_id"), "anomaly_type": a.get("anomaly_type"), "confidence": float(a.get("confidence", 0))}
            for a in anomalies
        ],
        "instruction": "Return a dict mapping anomaly index (0-based) to 'approved' or 'rejected'.",
    })

    approved = []
    for i, anomaly in enumerate(anomalies):
        decision = hitl_decisions.get(str(i), "rejected")
        if decision == "approved":
            approved.append(anomaly)

    return {
        "current_step": "hitl_completed",
        "approved_anomalies": approved,
        "hitl_decisions": hitl_decisions,
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
        "anomalies": state.get("approved_anomalies", state.get("anomalies", [])),
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


def route_after_hitl(state: PipelineState) -> str:
    approved = state.get("approved_anomalies", [])
    if approved:
        return "hypothesize"
    return "end"


class PharmaPipeline:
    """LangGraph-powered 5-stage pipeline with HITL interrupt"""

    def __init__(self):
        self.checkpointer = MemorySaver()
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(PipelineState)

        workflow.add_node("detect", detect_step)
        workflow.add_node("investigate", investigate_step)
        workflow.add_node("hitl_gate", hitl_gate_step)
        workflow.add_node("hypothesize", hypothesize_step)
        workflow.add_node("report", report_step)

        workflow.set_entry_point("detect")
        workflow.add_conditional_edges("detect", route_after_detection, {
            "investigate": "investigate",
            "end": END
        })
        workflow.add_edge("investigate", "hitl_gate")
        workflow.add_conditional_edges("hitl_gate", route_after_hitl, {
            "hypothesize": "hypothesize",
            "end": END
        })
        workflow.add_edge("hypothesize", "report")
        workflow.add_edge("report", END)

        return workflow.compile(checkpointer=self.checkpointer)

    async def run_detect_investigate(self, initial_input: Dict[str, Any]) -> Dict[str, Any]:
        """Run detect + investigate via LangGraph graph. Stops at HITL interrupt."""
        config = {"configurable": {"thread_id": "pipeline-main"}}
        initial_state = {
            "hours": initial_input.get("hours", 24),
            "tag_ids": initial_input.get("tag_ids", None),
        }

        result = await self.graph.ainvoke(initial_state, config=config)

        return {
            "tag_profiles": result.get("tag_profiles", {}),
            "anomalies": result.get("anomalies", []),
            "investigation_findings": result.get("investigation_findings", []),
            "hitl_required": result.get("hitl_required", False),
            "current_step": result.get("current_step", ""),
            "agent_reasoning": result.get("agent_reasoning", ""),
            "thread_id": "pipeline-main",
        }

    async def resume_after_hitl(self, hitl_decisions: Dict[str, str], thread_id: str = "pipeline-main") -> Dict[str, Any]:
        """Resume the graph after HITL approval, providing human decisions via Command."""
        config = {"configurable": {"thread_id": thread_id}}
        result = await self.graph.ainvoke(Command(resume=hitl_decisions), config=config)

        return {
            "approved_anomalies": result.get("approved_anomalies", []),
            "hypotheses": result.get("hypotheses", []),
            "reports": result.get("reports", {}),
            "current_step": result.get("current_step", ""),
            "agent_reasoning": result.get("agent_reasoning", ""),
        }