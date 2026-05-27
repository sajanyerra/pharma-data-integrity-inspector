"""
Agent 1: Detection Agent (ReAct)
Runs 9 deterministic baseline checks first, then uses a ReAct agent with tools
to investigate suspicious findings. The agent decides what to dig deeper into.
"""

import json
import numpy as np
from scipy import stats
from datetime import datetime, timedelta
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from .base import BaseAgent
from .detection_tools import set_detection_context
from config import settings


class DetectionAgent(BaseAgent):

    CORRELATED_PAIRS = [
        ("FI-101", "LI-101"), ("TI-201", "TI-202"), ("PI-501", "PI-502"),
        ("TI-601", "FI-601"), ("TI-101", "PI-101"), ("PI-301", "FI-301"),
        ("VI-301", "FI-301"),
    ]

    PHYSICAL_LIMITS = {
        "Temperature": {"min": -273.15, "max": 500},
        "Pressure": {"min": 0, "max": 100},
        "Flow": {"min": 0, "max": 10000},
        "Level": {"min": 0, "max": 100},
        "Vibration": {"min": 0, "max": 50},
        "Conductivity": {"min": 0, "max": 200},
    }

    ROC_THRESHOLDS = {"Temperature": 50, "Pressure": 20, "Flow": 200, "Level": 30}

    def __init__(self):
        super().__init__("DetectionAgent")
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL, temperature=0.1,
            api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL,
        )
        self.cross_sensor_groups = self._load_cross_sensor_groups()

    def _load_cross_sensor_groups(self) -> Dict:
        try:
            from tag_simulator import TagSimulator
            return TagSimulator(seed=42).CROSS_SENSOR_WITNESSES
        except Exception:
            return {
                'TI-101': {
                    'witnesses': ['PI-101', 'FI-201', 'LI-101'],
                    'relationships': {
                        'PI-101': {'coeff': 0.05, 'direction': 'same', 'desc': 'Higher reactor temp -> higher vapor pressure'},
                        'FI-201': {'coeff': -0.8, 'direction': 'opposite', 'desc': 'Higher reactor temp -> more cooling flow'},
                        'LI-101': {'coeff': 0.15, 'direction': 'same', 'desc': 'Temperature affects reaction rate'},
                    },
                },
            }

    async def _load_all_readings(self, hours: int) -> Dict[str, Dict]:
        """Load from DB if available, else generate simulated data on the fly."""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        all_rows = await self.db_conn.fetch(
            "SELECT tag_id, value, quality_code, timestamp FROM tag_readings WHERE timestamp >= $1 ORDER BY tag_id, timestamp",
            cutoff_time,
        )
        if len(all_rows) > 100:
            cache = {}
            for r in all_rows:
                tag_id = r["tag_id"]
                if tag_id not in cache:
                    cache[tag_id] = {"values": [], "timestamps": [], "quality_codes": []}
                if r["value"] is not None:
                    cache[tag_id]["values"].append(float(r["value"]))
                    cache[tag_id]["timestamps"].append(r["timestamp"])
                    cache[tag_id]["quality_codes"].append(r["quality_code"])
            for tag_id in cache:
                cache[tag_id]["values"] = np.array(cache[tag_id]["values"])
            if any(len(v["values"]) > 30 for v in cache.values()):
                return cache

        # Fallback: generate simulated data with anomalies (no DB needed)
        from tag_simulator import TagSimulator
        sim = TagSimulator(seed=42, start_time=datetime.utcnow() - timedelta(hours=hours))
        start = datetime.utcnow() - timedelta(hours=hours)
        cache = {}
        interval = 120  # 2-minute intervals = 720 readings/tag for 24h
        total_points = hours * 3600 // interval
        for i in range(total_points):
            ts = start + timedelta(seconds=i * interval)
            readings = sim.generate_all_tags(ts)
            for r in readings:
                tid = r["tag_id"]
                if tid not in cache:
                    cache[tid] = {"values": [], "timestamps": [], "quality_codes": []}
                cache[tid]["values"].append(r["value"])
                cache[tid]["timestamps"].append(ts)
                cache[tid]["quality_codes"].append(r.get("quality_code", "Good"))
        for tid in cache:
            cache[tid]["values"] = np.array(cache[tid]["values"])
        return cache

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run baseline checks, then ReAct agent to investigate."""
        await self.connect_db()
        try:
            hours = input_data.get("hours", 24)

            tags_result = await self.db_conn.fetch("SELECT * FROM tags")
            tag_metadata = {row["tag_id"]: dict(row) for row in tags_result}

            # If no tag metadata in DB, use simulator config
            if not tag_metadata:
                from tag_simulator import TagSimulator
                sim = TagSimulator(seed=42)
                # Build metadata from TAG_CONFIGS + get_tag_metadata
                meta_list = sim.get_tag_metadata()
                meta_map = {m["tag_id"]: m for m in meta_list}
                for tag_id, tc in sim.TAG_CONFIGS.items():
                    m = meta_map.get(tag_id, {})
                    tag_metadata[tag_id] = {
                        "tag_id": tag_id,
                        "tag_name": m.get("tag_name", tag_id),
                        "unit_type": m.get("unit_type", "Unknown"),
                        "data_type": tc.get("data_type", "Unknown"),
                        "normal_min": m.get("normal_min", 0),
                        "normal_max": m.get("normal_max", 100),
                        "description": m.get("description", ""),
                    }

            data_cache = await self._load_all_readings(hours)

            tag_profiles = {}
            for tag_id, td in data_cache.items():
                vals = td["values"]
                if len(vals) < 10:
                    continue
                meta = tag_metadata.get(tag_id, {})
                quality_codes = {}
                for qc in td["quality_codes"]:
                    quality_codes[qc] = quality_codes.get(qc, 0) + 1
                tag_profiles[tag_id] = {
                    "count": len(vals), "min": float(np.min(vals)), "max": float(np.max(vals)),
                    "mean": float(np.mean(vals)), "std": float(np.std(vals)),
                    "median": float(np.median(vals)), "q1": float(np.percentile(vals, 25)),
                    "q3": float(np.percentile(vals, 75)), "quality_codes": quality_codes,
                    "data_type": meta.get("data_type", "Unknown"),
                }

            # ── Phase 1: Deterministic baseline checks ──
            anomalies: List[Dict] = []
            for tag_id, profile in tag_profiles.items():
                data_type = profile.get("data_type", "Unknown")
                td = data_cache.get(tag_id)
                if not td or len(td["values"]) < 10:
                    continue
                vals = td["values"]
                tss = td["timestamps"]
                qcs = td["quality_codes"]
                readings = [{"value": v, "quality_code": qc, "timestamp": ts}
                            for v, qc, ts in zip(vals, qcs, tss)]

                a = self._check_sensor_drift(tag_id, vals, profile)
                if a: anomalies.append(a)
                a = self._check_stuck_value(tag_id, vals)
                if a: anomalies.append(a)
                a = self._check_impossible_readings(tag_id, vals, data_type)
                if a: anomalies.append(a)
                a = self._check_rate_of_change(tag_id, vals, readings, data_type)
                if a: anomalies.append(a)
                a = self._check_noise_burst(tag_id, vals, profile)
                if a: anomalies.append(a)

            anomalies.extend(self._check_correlations(data_cache))
            anomalies.extend(await self._check_pharma(data_cache, tag_metadata))
            anomalies.extend(self._check_cross_sensor(tag_profiles, data_cache))

            # Dedup: keep highest-confidence per tag, then cap at 4
            best = {}
            for a in anomalies:
                tid = a["tag_id"]
                if tid not in best or float(a.get("confidence", 0)) > float(best[tid].get("confidence", 0)):
                    best[tid] = a
            prio = {"cross_sensor_inconsistency": 0, "sensor_drift": 1, "stuck_value": 2,
                     "noise_burst": 3, "rate_of_change_violation": 4, "correlation_breakdown": 5,
                     "impossible_readings": 6, "cip_temperature_low": 7, "fda_audit_trail_concern": 8}
            final = sorted(best.values(), key=lambda a: (prio.get(a.get("anomaly_type", ""), 9), -float(a.get("confidence", 0))))[:4]

            # ── Phase 2: ReAct agent investigation ──
            from .detection_tools import get_tag_profile, check_correlation, check_cross_sensor, get_anomaly_summary, get_recent_readings
            tools = [get_tag_profile, check_correlation, check_cross_sensor, get_anomaly_summary, get_recent_readings]

            set_detection_context(data_cache, tag_profiles, tag_metadata, final, self.cross_sensor_groups)

            agent_reasoning = ""
            try:
                react_agent = create_react_agent(
                    model=self.llm,
                    tools=tools,
                    prompt="You are a pharma process engineer investigating sensor data integrity anomalies. "
                           "You have access to tools that let you examine individual sensors, check correlations, "
                           "and run cross-sensor corroboration checks. "
                           "Start by reviewing the baseline anomaly summary, then investigate any suspicious tags by "
                           "checking their profiles, correlations, and witness sensors. "
                           "Provide a concise 2-3 sentence assessment of: (1) what the pattern suggests, "
                           "(2) which anomaly is most urgent, (3) any systemic issue.",
                )

                anomaly_lines = [f"- {a['tag_id']}: {a['anomaly_type'].replace('_', ' ')} ({a.get('confidence', 0):.0%} confidence)"
                                 for a in final[:4]]
                anomaly_text = "\n".join(anomaly_lines) if final else "No anomalies found."

                result = await react_agent.ainvoke(
                    {"messages": [{"role": "user", "content": f"I just ran 9 integrity checks on 20 pharma sensors. Findings:\n{anomaly_text}\n\nPlease investigate further. Use the tools to check profiles, correlations, and cross-sensor relationships for any suspicious tags."}]},
                )

                for msg in result.get("messages", []):
                    if hasattr(msg, 'content') and msg.content and hasattr(msg, 'type'):
                        if msg.type == 'ai' and msg.content and not hasattr(msg, 'tool_calls'):
                            pass

                steps = []
                for msg in result.get("messages", []):
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        for tc in msg.tool_calls:
                            tool_name = tc.get('name', tc.get('function', {}).get('name', 'unknown'))
                            tool_args = tc.get('args', tc.get('function', {}).get('arguments', {}))
                            steps.append(f"Called {tool_name}({json.dumps(tool_args) if isinstance(tool_args, dict) else tool_args})")
                    elif hasattr(msg, 'type') and msg.type == 'tool':
                        content = msg.content[:200] if msg.content else ""
                        steps.append(f"Result: {content}")
                    elif hasattr(msg, 'content') and msg.content and not hasattr(msg, 'tool_calls'):
                        if msg.content.strip() and not any(c in msg.content for c in ['Called', 'Result:']):
                            steps.append(f"Agent: {msg.content.strip()}")

                agent_reasoning = "\n".join(steps) if steps else ""

            except Exception as e:
                print(f"[DetectionAgent] ReAct agent failed, using fallback: {e}")
                if final:
                    agent_reasoning = f"{len(final)} anomalies detected by baseline checks. Detailed investigation unavailable."

            result = {
                "anomalies": final,
                "tag_profiles": tag_profiles,
                "agent_reasoning": agent_reasoning,
                "summary": {"total_anomalies": len(final), "by_type": self._count_by_type(final),
                             "timestamp": datetime.utcnow().isoformat()},
            }

            await self.save_trace(input_data, result)
        finally:
            await self.disconnect_db()

        return result

    # ── baseline checks (same as before) ──────────────────────────────────

    def _check_sensor_drift(self, tag_id: str, values: np.ndarray, profile: Dict) -> Dict | None:
        n = len(values)
        if n < 30: return None
        iv = 86400.0 / n
        recent = max(10, int(3600 / iv))
        prev = max(30, int(21600 / iv))
        if recent + prev > n:
            recent, prev = max(10, n // 4), max(30, n // 2)
        recent_vals = values[-recent:]
        if recent + prev <= n:
            previous_vals = values[-(recent + prev):-recent]
        else:
            previous_vals = values[:prev]
        r_mean = float(np.mean(recent_vals))
        p_mean = float(np.mean(previous_vals))
        dev = abs(r_mean - p_mean) / (abs(p_mean) + 0.001) * 100
        rate = dev / 6
        if rate > 1.0:
            return {"tag_id": tag_id, "anomaly_type": "sensor_drift",
                    "confidence": min(0.9, rate / 10),
                    "evidence": {"recent_mean": round(r_mean, 3), "previous_mean": round(p_mean, 3),
                                  "deviation_percent": round(dev, 2), "drift_rate_per_hour": round(rate, 3)},
                    "timestamp": datetime.utcnow().isoformat(),
                    "severity": "high" if rate > 2 else "medium"}

    def _check_stuck_value(self, tag_id: str, values: np.ndarray) -> Dict | None:
        n = len(values)
        if n < 30: return None
        iv = 86400.0 / n
        ws = max(10, int(3600 / iv))
        step = max(ws // 2, 1)
        for start in range(0, n - ws + 1, step):
            w = values[start:start + ws]
            if len(np.unique(w)) < 3:
                return {"tag_id": tag_id, "anomaly_type": "stuck_value", "confidence": 0.95,
                        "evidence": {"unique_values_count": int(len(np.unique(w))),
                                      "stuck_value": round(float(w[0]), 3),
                                      "duration_hours": 1, "window_start_pct": round(start / n * 100, 1)},
                        "timestamp": datetime.utcnow().isoformat(), "severity": "high"}

    def _check_impossible_readings(self, tag_id: str, values: np.ndarray, data_type: str) -> Dict | None:
        limits = self.PHYSICAL_LIMITS.get(data_type)
        if not limits: return None
        mask = (values < limits["min"]) | (values > limits["max"])
        cnt = int(np.sum(mask))
        if cnt > 0:
            iv = values[mask]
            return {"tag_id": tag_id, "anomaly_type": "impossible_readings", "confidence": 1.0,
                    "evidence": {"count": cnt, "min_found": round(float(np.min(iv)), 3),
                                  "max_found": round(float(np.max(iv)), 3), "physical_limits": limits},
                    "timestamp": datetime.utcnow().isoformat(), "severity": "critical"}

    def _check_rate_of_change(self, tag_id: str, values: np.ndarray, readings: List, data_type: str) -> Dict | None:
        if len(values) < 30: return None
        diffs = np.diff(values)
        thresh = self.ROC_THRESHOLDS.get(data_type, 50)
        violations = int(np.sum(np.abs(diffs) > thresh))
        if violations > 10:
            return {"tag_id": tag_id, "anomaly_type": "rate_of_change_violation",
                    "confidence": min(0.95, violations / 20),
                    "evidence": {"violation_count": violations, "max_rate": round(float(np.max(np.abs(diffs))), 3),
                                  "threshold": thresh},
                    "timestamp": datetime.utcnow().isoformat(), "severity": "high"}

    def _check_noise_burst(self, tag_id: str, values: np.ndarray, profile: Dict) -> Dict | None:
        n = len(values)
        if n < 60 or "std" not in profile or profile["std"] <= 0: return None
        iv = 86400.0 / n if n > 0 else 30
        ws = max(30, int(1800 / iv))
        step = max(ws // 2, 1)
        best_ratio, best_start = 0, 0
        for start in range(0, n - ws, step):
            r = float(np.std(values[start:start + ws])) / profile["std"]
            if r > best_ratio: best_ratio, best_start = r, start
        if best_ratio > 5.0:
            return {"tag_id": tag_id, "anomaly_type": "noise_burst",
                    "confidence": min(0.85, best_ratio / 10),
                    "evidence": {"noise_multiplier": round(best_ratio, 2), "baseline_std": round(profile["std"], 3)},
                    "timestamp": datetime.utcnow().isoformat(), "severity": "medium"}

    def _check_correlations(self, data_cache: Dict) -> List[Dict]:
        anomalies = []
        for tag_a, tag_b in self.CORRELATED_PAIRS:
            a, b = data_cache.get(tag_a), data_cache.get(tag_b)
            if not a or not b or len(a["values"]) < 30 or len(b["values"]) < 30: continue
            va, vb = a["values"], b["values"]
            n = min(len(va), len(vb))
            va, vb = va[:n], vb[:n]
            if np.std(va) == 0 or np.std(vb) == 0: continue
            h = n // 2
            cf, _ = stats.pearsonr(va[:h], vb[:h])
            cs, _ = stats.pearsonr(va[h:], vb[h:])
            shift = abs(cs - cf)
            if shift > 0.8 and n > 50:
                anomalies.append({"tag_id": tag_a, "anomaly_type": "correlation_breakdown",
                                   "confidence": min(0.9, float(shift)),
                                   "evidence": {"pair": f"{tag_a} vs {tag_b}", "partner_tag": tag_b,
                                                  "shift": round(float(shift), 3), "n_readings": n},
                                   "timestamp": datetime.utcnow().isoformat(),
                                   "severity": "high" if shift > 0.8 else "medium"})
        return anomalies

    async def _check_pharma(self, data_cache: Dict, tag_metadata: Dict) -> List[Dict]:
        anomalies = []
        cip = {tid: td["values"] for tid, td in data_cache.items()
               if tag_metadata.get(tid, {}).get("unit_type") == "CIP System"}
        if "TI-601" in cip:
            lows = int(np.sum(cip["TI-601"] < 70))
            if lows > 30:
                anomalies.append({"tag_id": "TI-601", "anomaly_type": "cip_temperature_low",
                                    "confidence": min(0.9, lows / 100),
                                    "evidence": {"low_temp_readings": lows, "min_temp": round(float(np.min(cip["TI-601"])), 2), "threshold": 70},
                                    "timestamp": datetime.utcnow().isoformat(), "severity": "high",
                                    "pharma_impact": "Incomplete cleaning - contamination risk"})
        qa = await self.db_conn.fetch(
            "SELECT tag_id, quality_code, COUNT(*) as cnt FROM tag_readings "
            "WHERE timestamp >= NOW() - INTERVAL '24 hours' GROUP BY tag_id, quality_code")
        tq = {}
        for r in qa:
            tid = r["tag_id"]
            tq.setdefault(tid, {"total": 0, "bad": 0})
            tq[tid]["total"] += r["cnt"]
            if r["quality_code"] not in ("Good", None): tq[tid]["bad"] += r["cnt"]
        for tid, q in tq.items():
            if q["total"] > 100 and q["bad"] / q["total"] > 0.5:
                anomalies.append({"tag_id": tid, "anomaly_type": "fda_audit_trail_concern", "confidence": 0.7,
                                    "evidence": {"non_good_ratio": round(q["bad"] / q["total"], 3),
                                                  "total_readings": q["total"], "non_good_readings": q["bad"]},
                                    "timestamp": datetime.utcnow().isoformat(), "severity": "high",
                                    "pharma_impact": "21 CFR Part 11 compliance concern"})
        return anomalies

    def _check_cross_sensor(self, tag_profiles: Dict, data_cache: Dict) -> List[Dict]:
        anomalies = []
        for suspect_tag, config in self.cross_sensor_groups.items():
            if suspect_tag not in tag_profiles: continue
            sd = data_cache.get(suspect_tag)
            if not sd or len(sd["values"]) < 30: continue
            sv = sd["values"]
            n = len(sv)
            iv = 86400.0 / n if n > 0 else 30
            ws = max(30, int(3600 / iv))
            step = max(ws // 2, 1)
            hw = max(15, ws // 2)
            s_mean, s_std = float(np.mean(sv)), float(np.std(sv))
            if s_std == 0: continue
            contradictions = []
            for wit, rel in config["relationships"].items():
                wd = data_cache.get(wit)
                if not wd or len(wd["values"]) < 30: continue
                wv = wd["values"]
                w_std = float(np.std(wv))
                if w_std == 0: continue
                m = min(len(sv), len(wv))
                s, w = sv[:m], wv[:m]
                segs = []
                for st in range(0, m - ws, step):
                    ss, sw = s[st:st + ws], w[st:st + ws]
                    if np.std(ss) > 0 and np.std(sw) > 0:
                        sc, _ = stats.pearsonr(ss, sw)
                        segs.append(sc)
                if not segs: continue
                fw = min(3, len(segs))
                baseline = float(np.mean(segs[:fw]))
                recent = float(segs[-1])
                drop = baseline - recent
                if drop > 0.2 and abs(baseline) > 0.05:
                    sr, wr = sv[-ws:], wv[-ws:]
                    s_trend = float(np.mean(sr[-hw:]) - np.mean(sr[:hw]))
                    w_trend = float(np.mean(wr[-hw:]) - np.mean(wr[:hw]))
                    exp_dir = 1 if rel["direction"] == "same" else -1
                    contra = False
                    if exp_dir > 0:
                        if (s_trend > 0 and w_trend < -s_std * 0.1) or (s_trend < 0 and w_trend > s_std * 0.1): contra = True
                    else:
                        if (s_trend > 0 and w_trend > s_std * 0.1) or (s_trend < 0 and w_trend < -s_std * 0.1): contra = True
                    if contra or drop > 0.3:
                        contradictions.append({"witness": wit, "relationship": rel["desc"],
                                                "baseline_correlation": round(baseline, 3),
                                                "recent_correlation": round(recent, 3),
                                                "correlation_drop": round(drop, 3),
                                                "suspect_trend": round(s_trend, 3),
                                                "witness_trend": round(w_trend, 3),
                                                "trends_contradict": contra,
                                                "expected_direction": rel["direction"]})
            if contradictions:
                conf = min(0.95, 0.6 + 0.15 * len(contradictions))
                if any(c["trends_contradict"] for c in contradictions): conf = min(0.95, conf + 0.1)
                if len(contradictions) >= 2: conf = min(0.95, conf + 0.05)
                wsum = ", ".join(c["witness"] for c in contradictions)
                anomalies.append({"tag_id": suspect_tag, "anomaly_type": "cross_sensor_inconsistency",
                                   "confidence": round(conf, 2),
                                   "evidence": {"witness_count": len(contradictions), "witnesses": wsum,
                                                  "contradictions": contradictions,
                                                  "suspect_mean": round(s_mean, 3), "suspect_std": round(s_std, 3)},
                                   "timestamp": datetime.utcnow().isoformat(), "severity": "high",
                                   "pharma_impact": f"Sensor {suspect_tag} contradicts {wsum} — reading may be plausible but wrong.",
                                   "is_silent_lie": True})
        return anomalies

    def _count_by_type(self, anomalies: List[Dict]) -> Dict[str, int]:
        counts = {}
        for a in anomalies:
            counts[a["anomaly_type"]] = counts.get(a["anomaly_type"], 0) + 1
        return counts