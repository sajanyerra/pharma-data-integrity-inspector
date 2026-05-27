"""
Hypothesis Agent Tools — LangChain @tool functions for the ReAct hypothesis agent.
These tools let the agent investigate anomalies before forming root cause hypotheses.
"""

from langchain_core.tools import tool
from typing import Dict


_hypothesis_context: Dict = {}


def set_hypothesis_context(anomalies: list, tag_metadata: Dict, data_cache: Dict = None, tag_profiles: Dict = None):
    _hypothesis_context.clear()
    _hypothesis_context.update({
        "anomalies": anomalies,
        "tag_metadata": tag_metadata,
        "data_cache": data_cache or {},
        "tag_profiles": tag_profiles or {},
    })


@tool
def get_tag_details(tag_id: str) -> str:
    """Get detailed information about a sensor tag — its metadata, statistical profile,
    and any anomalies detected for it. Use this to understand a tag before forming a hypothesis.

    Args:
        tag_id: The sensor tag ID (e.g., 'TI-101', 'PI-101')
    """
    metadata = _hypothesis_context.get("tag_metadata", {})
    profiles = _hypothesis_context.get("tag_profiles", {})
    anomalies = _hypothesis_context.get("anomalies", [])

    tag_info = metadata.get(tag_id)
    if not tag_info:
        available = ", ".join(sorted(metadata.keys())[:10])
        return f"Tag '{tag_id}' not found. Available tags: {available}..."

    profile = profiles.get(tag_id, {})
    tag_anomalies = [a for a in anomalies if a.get("tag_id") == tag_id]

    result = f"Tag {tag_id} ({tag_info.get('tag_name', 'N/A')}):\n"
    result += f"  Unit: {tag_info.get('unit_type', 'Unknown')}, Type: {tag_info.get('data_type', 'Unknown')}\n"
    result += f"  Description: {tag_info.get('description', 'N/A')}\n"
    result += f"  Normal range: {tag_info.get('normal_min', '?')} - {tag_info.get('normal_max', '?')}\n"
    if profile:
        result += f"  Profile: mean={profile.get('mean', 0):.2f}, std={profile.get('std', 0):.2f}, "
        result += f"min={profile.get('min', 0):.2f}, max={profile.get('max', 0):.2f}\n"
    if tag_anomalies:
        for a in tag_anomalies:
            atype = a.get("anomaly_type", "unknown").replace("_", " ")
            conf = a.get("confidence", 0)
            result += f"  Anomaly: {atype} ({conf:.0%} confidence, {a.get('severity', 'unknown')} severity)\n"
    else:
        result += f"  No anomalies detected for this tag.\n"

    return result


@tool
def get_process_context(tag_id: str) -> str:
    """Get the process context for a tag — what unit it belongs to, what other tags
    are in the same unit, and what process conditions were happening. Use this to understand
    the environment around an anomaly.

    Args:
        tag_id: The sensor tag ID (e.g., 'TI-101')
    """
    metadata = _hypothesis_context.get("tag_metadata", {})
    anomalies = _hypothesis_context.get("anomalies", [])

    tag_info = metadata.get(tag_id)
    if not tag_info:
        return f"Tag '{tag_id}' not found."

    unit = tag_info.get("unit_type", "Unknown")
    same_unit = {tid: info for tid, info in metadata.items() if info.get("unit_type") == unit}

    result = f"Process context for {tag_id}:\n"
    result += f"  Unit: {unit}\n"
    result += f"  Tags in same unit: {', '.join(same_unit.keys())}\n"

    unit_anomalies = [a for a in anomalies if a.get("tag_id") in same_unit]
    if unit_anomalies:
        result += f"  Other anomalies in this unit: "
        result += ", ".join(f"{a['tag_id']} ({a.get('anomaly_type', 'unknown').replace('_', ' ')})" for a in unit_anomalies)
        result += "\n"
        result += "  This suggests a possible systemic issue within the unit rather than an isolated sensor fault.\n"
    else:
        result += f"  No other anomalies in this unit — likely an isolated sensor issue.\n"

    tag_anomalies = [a for a in anomalies if a.get("tag_id") == tag_id]
    for a in tag_anomalies:
        if a.get("anomaly_type") == "cross_sensor_inconsistency":
            witnesses = a.get("evidence", {}).get("witnesses", "")
            result += f"  Cross-sensor: contradicts witnesses {witnesses} — possible Silent Lie (sensor plausible but wrong)\n"

    return result


@tool
def get_similar_anomalies(anomaly_type: str) -> str:
    """Find all tags that have the same type of anomaly. Use this to see if the same
    issue is affecting multiple sensors — which would indicate a systemic problem rather
    than an isolated one.

    Args:
        anomaly_type: The anomaly type to search for (e.g., 'sensor_drift', 'stuck_value', 'cross_sensor_inconsistency')
    """
    anomalies = _hypothesis_context.get("anomalies", [])
    matching = [a for a in anomalies if a.get("anomaly_type") == anomaly_type]

    if not matching:
        all_types = sorted(set(a.get("anomaly_type", "unknown") for a in anomalies))
        return f"No anomalies of type '{anomaly_type}' found. Detected types: {', '.join(all_types)}"

    result = f"Found {len(matching)} anomaly(ies) of type '{anomaly_type}':\n"
    for a in matching:
        result += f"  - {a['tag_id']}: {a.get('confidence', 0):.0%} confidence, {a.get('severity', 'unknown')} severity\n"
        evidence = a.get("evidence", {})
        if isinstance(evidence, dict):
            for k, v in list(evidence.items())[:3]:
                if k != "contradictions":
                    result += f"    {k}: {v}\n"
    if len(matching) > 1:
        result += "\nMultiple tags with the same anomaly type suggests a systemic or environmental cause rather than isolated sensor failures."

    return result