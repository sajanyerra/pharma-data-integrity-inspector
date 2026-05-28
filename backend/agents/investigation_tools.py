"""
Investigation Agent Tools — 4 genuine tools that query simulated external systems.
The LLM decides which tools to call based on the anomaly type and what it found so far.
Different anomalies lead to different investigation paths — that's genuine agency.
"""

import json
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from langchain_core.tools import tool


_investigation_context: Dict = {}


def set_investigation_context(anomalies: list, tag_metadata: Dict, data_cache: Dict,
                              tag_profiles: Dict, cross_sensor_groups: Dict,
                              simulator=None, start_time=None):
    _investigation_context.clear()
    _investigation_context.update({
        "anomalies": anomalies,
        "tag_metadata": tag_metadata,
        "data_cache": data_cache,
        "tag_profiles": tag_profiles,
        "cross_sensor_groups": cross_sensor_groups,
        "simulator": simulator,
        "start_time": start_time or datetime.utcnow() - timedelta(hours=24),
    })


# ── Simulated External System APIs ──────────────────────────────────────

def _historian_api(tag_id: str, hours: int, resolution_min: int) -> Dict:
    """Simulated PI Historian — returns time series at requested resolution."""
    import numpy as np
    data_cache = _investigation_context.get("data_cache", {})
    td = data_cache.get(tag_id)
    if not td or len(td["values"]) < 10:
        return {"tag_id": tag_id, "error": "No data available for this tag."}
    vals = td["values"]
    n = len(vals)
    ts = _investigation_context.get("start_time", datetime.utcnow() - timedelta(hours=24))
    interval_sec = 86400.0 / n
    res_samples = max(1, int(resolution_min * 60 / interval_sec))
    window_samples = min(n, int(hours * 3600 / interval_sec))
    sliced = vals[-window_samples:]
    sampled = sliced[::res_samples]
    sampled_ts = [ts + timedelta(seconds=i * res_samples * interval_sec) for i in range(len(sampled))]
    if len(sampled) < 3:
        return {"tag_id": tag_id, "error": "Insufficient data for requested range/resolution."}
    mean_v = float(np.mean(sampled))
    std_v = float(np.std(sampled))
    recent_mean = float(np.mean(sampled[-max(1, len(sampled) // 4):]))
    earlier_mean = float(np.mean(sampled[:max(1, len(sampled) // 4)]))
    trend = "rising" if recent_mean > earlier_mean * 1.002 else "falling" if recent_mean < earlier_mean * 0.998 else "stable"
    return {
        "tag_id": tag_id,
        "hours": hours,
        "resolution_min": resolution_min,
        "points_returned": len(sampled),
        "mean": round(mean_v, 3),
        "std": round(std_v, 3),
        "min": round(float(np.min(sampled)), 3),
        "max": round(float(np.max(sampled)), 3),
        "trend": trend,
        "recent_mean": round(recent_mean, 3),
        "earlier_mean": round(earlier_mean, 3),
        "first_5": [round(float(v), 3) for v in sampled[:5]],
        "last_5": [round(float(v), 3) for v in sampled[-5:]],
    }


def _mes_api(tag_id: str, event_type: str) -> Dict:
    """Simulated MES/Batch system — returns process events near the anomaly."""
    sim = _investigation_context.get("simulator")
    meta = _investigation_context.get("tag_metadata", {})
    anomalies = _investigation_context.get("anomalies", [])
    tag_anomaly = next((a for a in anomalies if a.get("tag_id") == tag_id), {})
    anomaly_type = tag_anomaly.get("anomaly_type", "unknown")
    tag_info = meta.get(tag_id, {})
    unit = tag_info.get("unit_type", "Unknown")
    rng = random.Random(hash(tag_id) + hash(event_type))
    events = []
    start = _investigation_context.get("start_time", datetime.utcnow() - timedelta(hours=24))
    if event_type in ("grade_change", "batch_start"):
        if anomaly_type in ("sensor_drift", "correlation_breakdown") and rng.random() > 0.3:
            h = rng.randint(6, 14)
            events.append({
                "event": "Grade Change",
                "time": (start + timedelta(hours=h)).isoformat(),
                "from_grade": f"Grade-{rng.choice(['A', 'B', 'C'])}",
                "to_grade": f"Grade-{rng.choice(['D', 'E', 'F'])}",
                "unit": unit,
            })
        if rng.random() > 0.5:
            events.append({
                "event": "Batch Start",
                "time": (start + timedelta(hours=rng.randint(2, 10))).isoformat(),
                "batch_id": f"B-{rng.randint(1000, 9999)}",
                "product": rng.choice(["Product A", "Product B", "Product C"]),
                "unit": unit,
            })
    elif event_type == "equipment_startup":
        if anomaly_type in ("noise_burst", "rate_of_change_violation") and rng.random() > 0.4:
            events.append({
                "event": "Equipment Startup",
                "time": (start + timedelta(hours=rng.randint(4, 16))).isoformat(),
                "equipment": f"{unit} Package Unit",
                "reason": rng.choice(["Scheduled startup", "After maintenance", "Process demand"]),
            })
    elif event_type == "process_upset":
        if anomaly_type in ("rate_of_change_violation", "noise_burst") and rng.random() > 0.5:
            events.append({
                "event": "Process Upset",
                "time": (start + timedelta(hours=rng.randint(3, 12))).isoformat(),
                "description": rng.choice([
                    "Cooling water supply interruption",
                    "Steam header pressure drop",
                    "Raw material specification change",
                ]),
                "duration_min": rng.randint(5, 45),
                "unit": unit,
            })
    if not events:
        return {"tag_id": tag_id, "event_type": event_type, "events": [], "note": f"No {event_type} events found for this tag in the reporting period."}
    return {"tag_id": tag_id, "event_type": event_type, "events_found": len(events), "events": events}


def _cmms_api(tag_id: str) -> Dict:
    """Simulated CMMS — returns maintenance history for the instrument loop."""
    meta = _investigation_context.get("tag_metadata", {})
    anomalies = _investigation_context.get("anomalies", {})
    tag_anomaly = next((a for a in anomalies if a.get("tag_id") == tag_id), {})
    anomaly_type = tag_anomaly.get("anomaly_type", "unknown")
    rng = random.Random(hash(tag_id) + hash("maintenance"))
    tag_info = meta.get(tag_id, {})
    unit = tag_info.get("unit_type", "Unknown")
    start = _investigation_context.get("start_time", datetime.utcnow() - timedelta(hours=24))
    work_orders = []
    if anomaly_type in ("sensor_drift", "stuck_value", "rate_of_change_violation"):
        if rng.random() > 0.3:
            work_orders.append({
                "wo_id": f"WO-{rng.randint(10000, 99999)}",
                "type": "Calibration",
                "tag": tag_id,
                "completed": (start + timedelta(hours=rng.randint(-48, -2))).isoformat(),
                "technician": "Maintenance Team A",
                "notes": rng.choice([
                    "Routine calibration check",
                    "Post-repair recalibration",
                    "Sensor replaced and calibrated",
                ]),
            })
        if rng.random() > 0.7:
            work_orders.append({
                "wo_id": f"WO-{rng.randint(10000, 99999)}",
                "type": "Repair",
                "tag": tag_id,
                "completed": (start + timedelta(hours=rng.randint(-72, -12))).isoformat(),
                "technician": "Instrument Team B",
                "notes": rng.choice([
                    "Replaced transmitter board",
                    "Fixed loose wiring on analog input",
                    "Replaced thermowell",
                ]),
            })
    elif anomaly_type == "cross_sensor_inconsistency":
        if rng.random() > 0.5:
            work_orders.append({
                "wo_id": f"WO-{rng.randint(10000, 99999)}",
                "type": "Calibration",
                "tag": tag_id,
                "completed": (start + timedelta(hours=rng.randint(-48, -2))).isoformat(),
                "technician": "Maintenance Team A",
                "notes": "Partial calibration — range checked but no as-found/as-left data recorded",
            })
    else:
        if rng.random() > 0.8:
            work_orders.append({
                "wo_id": f"WO-{rng.randint(10000, 99999)}",
                "type": "Inspection",
                "tag": tag_id,
                "completed": (start + timedelta(hours=rng.randint(-24, -1))).isoformat(),
                "technician": "Round Inspector",
                "notes": "Visual inspection — no issues noted",
            })
    return {"tag_id": tag_id, "unit": unit, "work_orders_found": len(work_orders), "work_orders": work_orders}


def _lims_api(tag_id: str, param: str) -> Dict:
    """Simulated LIMS — returns lab results for batches near the anomaly."""
    rng = random.Random(hash(tag_id) + hash(param))
    meta = _investigation_context.get("tag_metadata", {})
    tag_info = meta.get(tag_id, {})
    start = _investigation_context.get("start_time", datetime.utcnow() - timedelta(hours=24))
    results = []
    for i in range(rng.randint(1, 3)):
        batch_time = start + timedelta(hours=rng.randint(4, 18))
        if param == "dissolution":
            results.append({
                "batch_id": f"B-{rng.randint(1000, 9999)}",
                "time": batch_time.isoformat(),
                "parameter": "Dissolution",
                "result": f"{rng.uniform(85, 102):.1f}%",
                "spec": "≥85% at 30 min",
                "status": "Pass" if rng.random() > 0.2 else "OOS",
            })
        elif param == "assay":
            results.append({
                "batch_id": f"B-{rng.randint(1000, 9999)}",
                "time": batch_time.isoformat(),
                "parameter": "Assay",
                "result": f"{rng.uniform(97, 103):.1f}%",
                "spec": "95.0-105.0%",
                "status": "Pass" if rng.random() > 0.15 else "OOS",
            })
        elif param == "impurity":
            results.append({
                "batch_id": f"B-{rng.randint(1000, 9999)}",
                "time": batch_time.isoformat(),
                "parameter": "Related Impurities",
                "result": f"{rng.uniform(0.05, 0.3):.2f}%",
                "spec": "≤0.5%",
                "status": "Pass" if rng.random() > 0.2 else "OOS",
            })
    any_oos = any(r.get("status") == "OOS" for r in results)
    return {
        "tag_id": tag_id,
        "parameter": param,
        "results": results,
        "batch_count": len(results),
        "any_out_of_spec": any_oos,
        "note": "Out-of-spec result detected — product impact possible" if any_oos else "All results within specification",
    }


# ── LangChain @tool Functions ────────────────────────────────────────────

@tool
def query_historian(tag_id: str, hours: int = 24, resolution_min: int = 15) -> str:
    """Query the PI Historian for a tag's time series at a specific time range and resolution.
    Use this to check trends, verify anomalies, or compare behavior over different periods.
    For drift: use hours=48, resolution_min=15 (slow trend).
    For spikes: use hours=1, resolution_min=1 (high-res short window).
    For stuck values: use hours=6, resolution_min=5 (medium window).
    For cross-sensor: use hours=24, resolution_min=5 (compare full period).

    Args:
        tag_id: The sensor tag ID (e.g., 'TI-101')
        hours: Time window in hours (1-48)
        resolution_min: Data resolution in minutes (1=high, 5=medium, 15=low)
    """
    result = _historian_api(tag_id, hours, resolution_min)
    if "error" in result:
        return result["error"]
    lines = [f"Historian data for {tag_id} (last {hours}h, {resolution_min}min resolution):",
             f"  {result['points_returned']} points, mean={result['mean']}, std={result['std']}",
             f"  min={result['min']}, max={result['max']}, trend={result['trend']}",
             f"  recent_mean={result['recent_mean']}, earlier_mean={result['earlier_mean']}"]
    if result.get("first_5"):
        lines.append(f"  First readings: {result['first_5']}")
    if result.get("last_5"):
        lines.append(f"  Last readings: {result['last_5']}")
    return "\n".join(lines)


@tool
def query_events(tag_id: str, event_type: str = "batch_start") -> str:
    """Query the MES/Batch system for process events near a tag's anomaly.
    Use this to check if a grade change, batch start, equipment startup, or process upset
    coincided with the anomaly. Different anomalies suggest different event types:
    - sensor_drift or correlation_breakdown → check grade_change or batch_start
    - noise_burst or rate_of_change → check equipment_startup or process_upset
    - cross_sensor → check grade_change (process conditions changed)

    Args:
        tag_id: The sensor tag ID (e.g., 'TI-101')
        event_type: Type of event to check: 'grade_change', 'batch_start', 'equipment_startup', 'process_upset'
    """
    result = _mes_api(tag_id, event_type)
    if not result.get("events"):
        return result.get("note", f"No {event_type} events found for {tag_id}.")
    lines = [f"Events for {tag_id} (type: {event_type}):"]
    for ev in result["events"]:
        lines.append(f"  - {ev['event']} at {ev['time']}")
        for k, v in ev.items():
            if k not in ("event", "time"):
                lines.append(f"    {k}: {v}")
    return "\n".join(lines)


@tool
def query_maintenance(tag_id: str) -> str:
    """Query the CMMS for recent maintenance on a tag's instrument loop.
    Use this when you suspect the anomaly might be related to recent work —
    especially for drift, stuck values, or post-maintenance calibration issues.
    Do NOT call this for noise_burst or cross_sensor_inconsistency (unlikely maintenance-related).

    Args:
        tag_id: The sensor tag ID (e.g., 'TI-101')
    """
    result = _cmms_api(tag_id)
    if not result.get("work_orders"):
        return f"No recent maintenance found for {tag_id} ({result.get('unit', 'Unknown')} unit)."
    lines = [f"Maintenance history for {tag_id} ({result.get('unit', 'Unknown')}):"]
    for wo in result["work_orders"]:
        lines.append(f"  - {wo['wo_id']}: {wo['type']} completed {wo['completed']}")
        lines.append(f"    Notes: {wo['notes']}")
    return "\n".join(lines)


@tool
def query_lab_results(tag_id: str, param: str = "assay") -> str:
    """Query LIMS for lab test results to check if the anomaly affected product quality.
    Use this ONLY when product impact is suspected — e.g., cross_sensor_inconsistency
    (sensor plausible but wrong), high-severity anomalies, or CIP temperature issues.
    Do NOT call this for noise_burst or minor drift (unlikely product impact).

    Args:
        tag_id: The sensor tag ID (e.g., 'TI-101')
        param: Lab parameter to check: 'dissolution', 'assay', 'impurity'
    """
    result = _lims_api(tag_id, param)
    lines = [f"Lab results for {tag_id} (parameter: {param}):",
             f"  {result['batch_count']} batch(es) tested"]
    for r in result.get("results", []):
        lines.append(f"  - {r['batch_id']}: {r['parameter']}={r['result']} (spec: {r['spec']}, {r['status']})")
    lines.append(f"  {result.get('note', '')}")
    return "\n".join(lines)