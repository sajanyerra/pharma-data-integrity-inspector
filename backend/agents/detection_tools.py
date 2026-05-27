"""
Detection Agent Tools — LangChain @tool functions for the ReAct detection agent.
These tools let the agent investigate specific tags, correlations, and cross-sensor relationships.
Data is injected at runtime (not hardcoded) so tools operate on the actual DB data.
"""

from langchain_core.tools import tool
import numpy as np
from scipy import stats
from typing import Dict, Optional


_detection_context: Dict = {}


def set_detection_context(data_cache: Dict, tag_profiles: Dict, tag_metadata: Dict,
                          baseline_anomalies: list, cross_sensor_groups: Dict):
    _detection_context.clear()
    _detection_context.update({
        "data_cache": data_cache,
        "tag_profiles": tag_profiles,
        "tag_metadata": tag_metadata,
        "baseline_anomalies": baseline_anomalies,
        "cross_sensor_groups": cross_sensor_groups,
    })


@tool
def get_tag_profile(tag_id: str) -> str:
    """Get the statistical profile for a sensor tag — mean, std, min, max, quartiles, data type.
    Use this to understand a tag's normal behavior before investigating anomalies.

    Args:
        tag_id: The sensor tag identifier (e.g., 'TI-101', 'PI-101', 'FI-201')
    """
    profiles = _detection_context.get("tag_profiles", {})
    if tag_id not in profiles:
        available = ", ".join(sorted(profiles.keys())[:10])
        return f"Tag '{tag_id}' not found. Available tags include: {available}..."
    p = profiles[tag_id]
    return (f"Tag {tag_id} ({p.get('data_type', 'Unknown')}): "
            f"mean={p['mean']:.2f}, std={p['std']:.2f}, "
            f"min={p['min']:.2f}, max={p['max']:.2f}, "
            f"Q1={p['q1']:.2f}, Q3={p['q3']:.2f}, "
            f"n={p['count']} readings, "
            f"quality_codes={p.get('quality_codes', {})}")


@tool
def check_correlation(tag_a: str, tag_b: str) -> str:
    """Compute the Pearson correlation between two tags and check if their relationship has shifted.
    Returns overall correlation, first-half correlation, second-half correlation, and shift magnitude.

    Args:
        tag_a: First sensor tag ID (e.g., 'TI-101')
        tag_b: Second sensor tag ID (e.g., 'PI-101')
    """
    data_cache = _detection_context.get("data_cache", {})
    a_data = data_cache.get(tag_a)
    b_data = data_cache.get(tag_b)
    if not a_data or not b_data:
        return f"One or both tags not found in data cache."
    va, vb = a_data["values"], b_data["values"]
    if len(va) < 30 or len(vb) < 30:
        return f"Not enough data for correlation (need 30+ readings per tag)."
    n = min(len(va), len(vb))
    va, vb = va[:n], vb[:n]
    if np.std(va) == 0 or np.std(vb) == 0:
        return f"One or both tags have zero variance — cannot compute correlation."
    overall_r, _ = stats.pearsonr(va, vb)
    h = n // 2
    first_r, _ = stats.pearsonr(va[:h], vb[:h])
    second_r, _ = stats.pearsonr(va[h:], vb[h:])
    shift = abs(second_r - first_r)
    status = "SHIFTED" if shift > 0.5 else "STABLE"
    return (f"Correlation {tag_a} vs {tag_b}: overall={overall_r:.3f}, "
            f"first_half={first_r:.3f}, second_half={second_r:.3f}, "
            f"shift={shift:.3f} ({status})")


@tool
def check_cross_sensor(tag_id: str) -> str:
    """Check if a tag contradicts its physically-correlated witness sensors.
    This is the novel Cross-Sensor Corroboration check — it catches sensors that read
    plausibly within range but are wrong because their witnesses tell a different story.

    Args:
        tag_id: The suspect sensor tag ID (e.g., 'TI-101')
    """
    cross_groups = _detection_context.get("cross_sensor_groups", {})
    data_cache = _detection_context.get("data_cache", {})
    profiles = _detection_context.get("tag_profiles", {})

    if tag_id not in cross_groups:
        tags_with_witnesses = ", ".join(sorted(cross_groups.keys()))
        return f"Tag '{tag_id}' has no witness group. Tags with witnesses: {tags_with_witnesses}"

    config = cross_groups[tag_id]
    sd = data_cache.get(tag_id)
    if not sd or len(sd["values"]) < 30:
        return f"Not enough data for tag {tag_id}."

    sv = sd["values"]
    n = len(sv)
    iv = 86400.0 / n if n > 0 else 30
    ws = max(30, int(3600 / iv))
    step = max(ws // 2, 1)
    hw = max(15, ws // 2)
    s_mean, s_std = float(np.mean(sv)), float(np.std(sv))
    if s_std == 0:
        return f"Tag {tag_id} has zero variance."

    results = []
    for wit, rel in config["relationships"].items():
        wd = data_cache.get(wit)
        if not wd or len(wd["values"]) < 30:
            continue
        wv = wd["values"]
        w_std = float(np.std(wv))
        if w_std == 0:
            continue
        m = min(len(sv), len(wv))
        s, w = sv[:m], wv[:m]
        segs = []
        for st in range(0, m - ws, step):
            ss, sw = s[st:st + ws], w[st:st + ws]
            if np.std(ss) > 0 and np.std(sw) > 0:
                sc, _ = stats.pearsonr(ss, sw)
                segs.append(sc)
        if not segs:
            continue
        fw = min(3, len(segs))
        baseline = float(np.mean(segs[:fw]))
        recent = float(segs[-1])
        drop = baseline - recent
        sr, wr = sv[-ws:], wv[-ws:]
        s_trend = float(np.mean(sr[-hw:]) - np.mean(sr[:hw]))
        w_trend = float(np.mean(wr[-hw:]) - np.mean(wr[:hw]))
        exp_dir = 1 if rel["direction"] == "same" else -1
        contradicts = False
        if exp_dir > 0:
            if (s_trend > 0 and w_trend < -s_std * 0.1) or (s_trend < 0 and w_trend > s_std * 0.1):
                contradicts = True
        else:
            if (s_trend > 0 and w_trend > s_std * 0.1) or (s_trend < 0 and w_trend < -s_std * 0.1):
                contradicts = True
        results.append(f"  {wit}: baseline_r={baseline:.3f}, recent_r={recent:.3f}, "
                       f"drop={drop:.3f}, suspect_trend={s_trend:.3f}, witness_trend={w_trend:.3f}, "
                       f"expected={rel['direction']}, contradicts={'YES' if contradicts else 'no'}")

    if not results:
        return f"Cross-sensor check for {tag_id}: no valid witness data available."
    header = f"Cross-sensor check for {tag_id} (mean={s_mean:.2f}, std={s_std:.2f}):"
    return header + "\n" + "\n".join(results)


@tool
def get_anomaly_summary() -> str:
    """Get a summary of anomalies already detected by the baseline rule checks.
    Use this to understand what the deterministic rules found before deciding if deeper investigation is needed.

    Returns:
        A formatted summary of all detected anomalies.
    """
    anomalies = _detection_context.get("baseline_anomalies", [])
    if not anomalies:
        return "No anomalies detected by baseline checks. All 9 rule-based checks passed across all tags."
    lines = []
    for a in anomalies:
        atype = a.get("anomaly_type", "unknown").replace("_", " ")
        tid = a.get("tag_id", "unknown")
        conf = a.get("confidence", 0)
        sev = a.get("severity", "unknown")
        evidence = a.get("evidence", {})
        if isinstance(evidence, dict):
            ev_str = ", ".join(f"{k}={v}" for k, v in list(evidence.items())[:3])
        else:
            ev_str = str(evidence)[:80]
        lines.append(f"- {tid}: {atype} ({conf:.0%} confidence, {sev}) — {ev_str}")
    return f"Baseline detected {len(anomalies)} anomalies:\n" + "\n".join(lines)


@tool
def get_recent_readings(tag_id: str, last_n: int = 10) -> str:
    """Get the most recent readings for a tag to see its current behavior.
    Returns the last N values and timestamps so you can spot recent trends.

    Args:
        tag_id: The sensor tag ID (e.g., 'TI-101')
        last_n: Number of recent readings to return (default 10, max 50)
    """
    data_cache = _detection_context.get("data_cache", {})
    td = data_cache.get(tag_id)
    if not td:
        profiles = _detection_context.get("tag_profiles", {})
        available = ", ".join(sorted(profiles.keys())[:10])
        return f"Tag '{tag_id}' not found. Available tags: {available}..."
    vals = td["values"]
    tss = td["timestamps"]
    qcs = td["quality_codes"]
    n = min(last_n, 50, len(vals))
    recent_vals = vals[-n:] if hasattr(vals, '__getitem__') else list(vals[-n:])
    recent_qcs = qcs[-n:]
    recent_ts = tss[-n:] if tss else []
    lines = []
    for i in range(n):
        ts = recent_ts[i].isoformat() if hasattr(recent_ts[i], 'isoformat') else str(recent_ts[i]) if i < len(recent_ts) else ""
        lines.append(f"  {ts}: {recent_vals[i]:.2f} ({recent_qcs[i]})")
    mean_recent = float(np.mean(recent_vals))
    std_recent = float(np.std(recent_vals))
    return f"Last {n} readings for {tag_id} (mean={mean_recent:.2f}, std={std_recent:.2f}):\n" + "\n".join(lines)