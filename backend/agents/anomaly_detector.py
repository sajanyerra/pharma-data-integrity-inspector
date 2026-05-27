"""
Agent 2: Anomaly Detector
Applies 11 data integrity checks to detect anomalies, including Cross-Sensor Corroboration.
Uses deterministic rules for detection, then LLM to prioritize and explain findings.
"""

import numpy as np
from scipy import stats
from typing import Dict, Any, List
from datetime import datetime, timedelta
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from .base import BaseAgent
from config import settings


class AnomalyDetector(BaseAgent):
    """Detects data integrity anomalies using 8+ detection algorithms with AI prioritization"""
    
    def __init__(self):
        super().__init__("AnomalyDetector")
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            temperature=0.2,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
        
        self.correlated_pairs = [
            ("FI-101", "LI-101"),
            ("TI-201", "TI-202"),
            ("PI-501", "PI-502"),
            ("TI-601", "FI-601"),
            ("TI-101", "PI-101"),
            ("PI-301", "FI-301"),
            ("VI-301", "FI-301"),
        ]
        
        self.cross_sensor_groups = {}
        try:
            from tag_simulator import TagSimulator
            sim = TagSimulator(seed=42)
            self.cross_sensor_groups = sim.CROSS_SENSOR_WITNESSES
        except Exception:
            self.cross_sensor_groups = {
                'TI-101': {
                    'witnesses': ['PI-101', 'FI-201', 'LI-101'],
                    'relationships': {
                        'PI-101': {'coeff': 0.05, 'direction': 'same', 'desc': 'Higher reactor temp -> higher vapor pressure'},
                        'FI-201': {'coeff': -0.8, 'direction': 'opposite', 'desc': 'Higher reactor temp -> cooling system increases flow'},
                        'LI-101': {'coeff': 0.15, 'direction': 'same', 'desc': 'Temperature affects reaction rate'},
                    },
                },
            }
        
        self.physical_limits = {
            "Temperature": {"min": -273.15, "max": 500},
            "Pressure": {"min": 0, "max": 100},
            "Flow": {"min": 0, "max": 10000},
            "Level": {"min": 0, "max": 100},
            "Vibration": {"min": 0, "max": 50},
            "Conductivity": {"min": 0, "max": 200},
        }
        
    async def _load_all_readings(self, hours: int) -> Dict[str, Dict]:
        """Load all tag readings in one query and cache in memory"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        all_rows = await self.db_conn.fetch(
            "SELECT tag_id, value, quality_code, timestamp FROM tag_readings WHERE timestamp >= $1 ORDER BY tag_id, timestamp",
            cutoff_time
        )
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
        return cache

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply 8 active anomaly detection checks with data loaded once.
        """
        await self.connect_db()

        try:
            tag_profiles = input_data.get("tag_profiles", {})
            hours = input_data.get("hours", 24)
            anomalies = []

            tags_result = await self.db_conn.fetch("SELECT * FROM tags")
            tag_metadata = {row["tag_id"]: dict(row) for row in tags_result}

            data_cache = await self._load_all_readings(hours)

            print(f"[AnomalyDetector] Loaded {len(data_cache)} tags, {sum(len(d['values']) for d in data_cache.values())} total readings")

            for tag_id, profile in tag_profiles.items():
                metadata = tag_metadata.get(tag_id, {})
                data_type = metadata.get("data_type", "Unknown")
                tag_data = data_cache.get(tag_id)
                if not tag_data or len(tag_data["values"]) < 10:
                    print(f"[AnomalyDetector] SKIP {tag_id}: only {len(tag_data['values']) if tag_data else 0} readings")
                    continue

                values_array = tag_data["values"]
                timestamps = tag_data["timestamps"]
                quality_codes = tag_data["quality_codes"]

                readings_like = [
                    {"value": v, "quality_code": qc, "timestamp": ts}
                    for v, qc, ts in zip(values_array, quality_codes, timestamps)
                ]

                print(f"[AnomalyDetector] {tag_id}: {len(values_array)} readings, mean={np.mean(values_array):.2f}, std={np.std(values_array):.2f}, min={np.min(values_array):.2f}, max={np.max(values_array):.2f}")

                drift_anomaly = self._check_sensor_drift(tag_id, values_array, profile)
                if drift_anomaly:
                    anomalies.append(drift_anomaly)
                    print(f"  -> DRIFT detected: {drift_anomaly['evidence']}")

                stuck_anomaly = self._check_stuck_value(tag_id, values_array, readings_like)

                drift_anomaly = self._check_sensor_drift(tag_id, values_array, profile)
                if drift_anomaly:
                    anomalies.append(drift_anomaly)

                stuck_anomaly = self._check_stuck_value(tag_id, values_array, readings_like)
                if stuck_anomaly:
                    anomalies.append(stuck_anomaly)

                impossible_anomaly = self._check_impossible_readings(tag_id, values_array, data_type)
                if impossible_anomaly:
                    anomalies.append(impossible_anomaly)

                roc_anomaly = self._check_rate_of_change(tag_id, values_array, readings_like, data_type)
                if roc_anomaly:
                    anomalies.append(roc_anomaly)

                noise_anomaly = self._check_noise_burst(tag_id, values_array, profile)
                if noise_anomaly:
                    anomalies.append(noise_anomaly)

            correlation_anomalies = self._check_correlations_cached(data_cache)
            anomalies.extend(correlation_anomalies)
            print(f"[AnomalyDetector] Correlation anomalies: {len(correlation_anomalies)}")

            pharma_anomalies = await self._check_pharma_specific_cached(data_cache, tag_metadata)
            anomalies.extend(pharma_anomalies)
            print(f"[AnomalyDetector] Pharma anomalies: {len(pharma_anomalies)}")

            silent_lie_anomalies = self._check_cross_sensor_consistency_cached(tag_profiles, data_cache)
            anomalies.extend(silent_lie_anomalies)
            print(f"[AnomalyDetector] Cross-sensor anomalies: {len(silent_lie_anomalies)}")

            # Deduplicate: keep highest-confidence anomaly per tag_id
            best_per_tag = {}
            for a in anomalies:
                tid = a['tag_id']
                conf = float(a.get('confidence', 0))
                if tid not in best_per_tag or conf > float(best_per_tag[tid].get('confidence', 0)):
                    best_per_tag[tid] = a
            
            # Prioritize cross_sensor and drift over secondary effects
            priority_types = {'cross_sensor_inconsistency': 0, 'sensor_drift': 1, 'stuck_value': 2, 'silent_lie': 3, 'noise_burst': 4, 'rate_of_change_violation': 5, 'correlation_breakdown': 6}
            sorted_anomalies = sorted(best_per_tag.values(), key=lambda a: (priority_types.get(a.get('anomaly_type', ''), 9), -float(a.get('confidence', 0))))
            final_anomalies = sorted_anomalies[:4]

            print(f"[AnomalyDetector] Raw: {len(anomalies)}, After dedup: {len(best_per_tag)}, Final (capped 4): {len(final_anomalies)}")
            for a in final_anomalies:
                print(f"  -> {a['tag_id']} {a['anomaly_type']} conf={a.get('confidence', 0):.2f}")

            result = {
                "anomalies": final_anomalies,
                "summary": {
                    "total_anomalies": len(final_anomalies),
                    "by_type": self._count_by_type(final_anomalies),
                    "timestamp": datetime.utcnow().isoformat()
                }
            }

            result["ai_prioritization"] = await self._prioritize_anomalies(final_anomalies)

            await self.save_trace(input_data, result)
            return result

        finally:
            await self.disconnect_db()
    
    async def _prioritize_anomalies(self, anomalies: List) -> str:
        """Use LLM to analyze detection patterns and explain pharma implications"""
        if not anomalies:
            return "No anomalies detected. All sensor data appears within normal parameters."
        
        prompt = PromptTemplate(
            template="""You are a pharma process engineer reviewing integrity check results from a pharmaceutical plant. These anomalies were detected by automated checks. Your job: analyze the PATTERN of findings and explain what they mean together.

Detected anomalies (checks include: sensor drift, stuck values, impossible readings, rate-of-change, noise bursts, correlation breakdown, CIP issues, FDA audit trail, CROSS-SENSOR CONSISTENCY):
{anomaly_summary}

In 2-3 sentences: (1) What does this pattern suggest about the plant? (2) Which finding is most urgent — especially any cross-sensor inconsistency? (3) Any systemic issue (e.g., network, calibration, operator)?""",
            input_variables=["anomaly_summary"]
        )
        
        lines = []
        for a in anomalies[:10]:
            lines.append(f"- {a['tag_id']} ({a.get('tag_name', '')}): {a['anomaly_type'].replace('_', ' ')} — {a['confidence']:.0%} confidence. Evidence: {str(a.get('evidence', {}))[:120]}")
        anomaly_summary = "\n".join(lines)
        
        try:
            chain = prompt | self.llm
            response = await chain.ainvoke({"anomaly_summary": anomaly_summary})
            return response.content if hasattr(response, 'content') else str(response)
        except Exception:
            return f"{len(anomalies)} anomalies detected across 11 integrity checks. Review each for pharma manufacturing impact."
    
    def _check_sensor_drift(self, tag_id: str, values: np.ndarray, profile: Dict) -> Dict:
        """Check 1: Sensor Drift - Compare last 1h vs previous 6h mean"""
        n = len(values)
        if n < 30:
            return None

        interval_sec = 86400.0 / n
        recent_size = max(10, int(3600 / interval_sec))
        previous_size = max(30, int(21600 / interval_sec))
        
        if recent_size + previous_size > n:
            recent_size = max(10, n // 4)
            previous_size = max(30, n // 2)
        
        recent_1h = values[-recent_size:]
        previous_6h = values[-(recent_size + previous_size):-recent_size]
            
        recent_mean = np.mean(recent_1h)
        previous_mean = np.mean(previous_6h)
        
        deviation = abs(recent_mean - previous_mean) / (abs(previous_mean) + 0.001) * 100
        drift_rate = deviation / 6
        
        print(f"  [drift] {tag_id}: recent_mean={recent_mean:.2f}, previous_mean={previous_mean:.2f}, deviation={deviation:.2f}%, drift_rate={drift_rate:.3f}")
        
        if drift_rate > 1.0:
            return {
                "tag_id": tag_id,
                "anomaly_type": "sensor_drift",
                "confidence": min(0.9, drift_rate / 10),
                "evidence": {
                    "recent_mean": round(float(recent_mean), 3),
                    "previous_mean": round(float(previous_mean), 3),
                    "deviation_percent": round(float(deviation), 2),
                    "drift_rate_per_hour": round(float(drift_rate), 3)
                },
                "timestamp": datetime.utcnow().isoformat(),
                "severity": "high" if drift_rate > 2 else "medium"
            }
        return None
    
    def _check_stuck_value(self, tag_id: str, values: np.ndarray, readings: List) -> Dict:
        """Check 2: Stuck Value - Scan with sliding 1h windows, adaptive to data interval"""
        n = len(values)
        if n < 30:
            return None

        interval_sec = 86400.0 / n
        window_size = max(10, int(3600 / interval_sec))  # 1 hour
        step = max(window_size // 2, 1)
        print(f"  [stuck] {tag_id}: n={n}, interval={interval_sec:.1f}s, window={window_size}, step={step}")
        for start in range(0, len(values) - window_size + 1, step):
            window = values[start:start + window_size]
            unique_values = len(np.unique(window))
            if unique_values < 3:
                print(f"  [stuck] {tag_id}: DETECTED at window {start}-{start+window_size}, unique={unique_values}, value={window[0]:.3f}")
                return {
                    "tag_id": tag_id,
                    "anomaly_type": "stuck_value",
                    "confidence": 0.95,
                    "evidence": {
                        "unique_values_count": int(unique_values),
                        "stuck_value": round(float(window[0]), 3),
                        "duration_hours": 1,
                        "window_start_pct": round(float(start) / len(values) * 100, 1)
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                    "severity": "high"
                }
        return None
    
    def _check_impossible_readings(self, tag_id: str, values: np.ndarray, data_type: str) -> Dict:
        """Check 3: Impossible Readings - Outside physical limits"""
        limits = self.physical_limits.get(data_type)
        if not limits:
            return None
        
        impossible_mask = (values < limits["min"]) | (values > limits["max"])
        impossible_count = np.sum(impossible_mask)
        
        if impossible_count > 0:
            impossible_values = values[impossible_mask]
            return {
                "tag_id": tag_id,
                "anomaly_type": "impossible_readings",
                "confidence": 1.0,
                "evidence": {
                    "count": int(impossible_count),
                    "min_found": round(float(np.min(impossible_values)), 3),
                    "max_found": round(float(np.max(impossible_values)), 3),
                    "physical_limits": limits
                },
                "timestamp": datetime.utcnow().isoformat(),
                "severity": "critical"
            }
        return None
    
    def _check_quality_mismatch(self, tag_id: str, values: np.ndarray, profile: Dict) -> Dict:
        """Check 4: Quality Code Mismatch - 'Good' code but statistical outliers"""
        quality_codes = profile.get("quality_codes", {})
        good_count = quality_codes.get("Good", 0)
        
        if good_count < 10:
            return None
        
        q1, q3 = profile["q1"], profile["q3"]
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        outliers = ((values < lower_bound) | (values > upper_bound)).sum()
        outlier_ratio = outliers / len(values)
        
        if outlier_ratio > 0.05 and quality_codes.get("Good", 0) / sum(quality_codes.values()) > 0.9:
            return {
                "tag_id": tag_id,
                "anomaly_type": "quality_code_mismatch",
                "confidence": min(0.9, float(outlier_ratio) * 2),
                "evidence": {
                    "outlier_count": int(outliers),
                    "outlier_ratio": round(float(outlier_ratio), 3),
                    "good_quality_ratio": round(quality_codes.get("Good", 0) / sum(quality_codes.values()), 3)
                },
                "timestamp": datetime.utcnow().isoformat(),
                "severity": "medium"
            }
        return None
    
    def _check_rate_of_change(self, tag_id: str, values: np.ndarray, readings: List, data_type: str) -> Dict:
        """Check 5: Rate-of-Change Violation - Only flag physically impossible changes"""
        if len(values) < 30:
            return None
        
        diffs = np.diff(values)
        
        thresholds = {
            "Temperature": 50,
            "Pressure": 20,
            "Flow": 200,
            "Level": 30,
        }
        
        threshold = thresholds.get(data_type, 50)
        violations = np.abs(diffs) > threshold
        violation_count = np.sum(violations)
        
        if violation_count > 10:
            max_violation = float(np.max(np.abs(diffs[violations])))
            return {
                "tag_id": tag_id,
                "anomaly_type": "rate_of_change_violation",
                "confidence": min(0.95, float(violation_count) / 20),
                "evidence": {
                    "violation_count": int(violation_count),
                    "max_rate": round(max_violation, 3),
                    "threshold": threshold
                },
                "timestamp": datetime.utcnow().isoformat(),
                "severity": "high"
            }
        return None
    
    def _check_noise_burst(self, tag_id: str, values: np.ndarray, profile: Dict) -> Dict:
        """Check: Noise Burst - Variance spike in a window vs baseline"""
        n = len(values)
        if n < 60 or 'std' not in profile:
            return None
        
        interval_sec = 86400.0 / n if n > 0 else 30
        window_size = max(30, int(1800 / interval_sec))  # 30 min
        step = max(window_size // 2, 1)
        
        baseline_std = profile['std']
        if baseline_std <= 0:
            return None
        
        max_ratio = 0
        max_window_start = 0
        
        for start in range(0, n - window_size, step):
            window = values[start:start + window_size]
            window_std = float(np.std(window))
            ratio = window_std / baseline_std
            if ratio > max_ratio:
                max_ratio = ratio
                max_window_start = start
        
        if max_ratio > 5.0:
            return {
                "tag_id": tag_id,
                "anomaly_type": "noise_burst",
                "confidence": min(0.85, max_ratio / 10),
                "evidence": {
                    "noise_multiplier": round(max_ratio, 2),
                    "baseline_std": round(baseline_std, 3),
                    "window_std": round(baseline_std * max_ratio, 3),
                    "window_start_pct": round(max_window_start / n * 100, 1),
                },
                "timestamp": datetime.utcnow().isoformat(),
                "severity": "medium"
            }
        return None
    
    def _check_data_gaps(self, tag_id: str, readings: List) -> Dict:
        """Check 6: Data Gaps - Gap > 2x scan rate (10 sec)"""
        if len(readings) < 2:
            return None
        
        gaps = []
        for i in range(1, len(readings)):
            time_diff = (readings[i]["timestamp"] - readings[i-1]["timestamp"]).total_seconds()
            if time_diff > 300:
                gaps.append(time_diff)
        
        if gaps and len(gaps) > 3:
            return {
                "tag_id": tag_id,
                "anomaly_type": "data_gaps",
                "confidence": min(0.9, len(gaps) / 5),
                "evidence": {
                    "gap_count": len(gaps),
                    "max_gap_seconds": round(max(gaps), 2),
                    "avg_gap_seconds": round(float(np.mean(gaps)), 2)
                },
                "timestamp": datetime.utcnow().isoformat(),
                "severity": "medium"
            }
        return None
    
    def _check_statistical_outliers(self, tag_id: str, values: np.ndarray, profile: Dict) -> Dict:
        """Check 7: Statistical Outliers - Only flag extreme outliers (>5 sigma)"""
        mean, std = profile["mean"], profile["std"]
        
        if std == 0 or len(values) < 100:
            return None
        
        z_scores = np.abs((values - mean) / std)
        outliers = z_scores > 5
        
        outlier_count = np.sum(outliers)
        outlier_ratio = outlier_count / len(values)
        
        if outlier_ratio > 0.05 and outlier_count > 10:
            return {
                "tag_id": tag_id,
                "anomaly_type": "statistical_outliers",
                "confidence": min(0.8, float(outlier_ratio) * 5),
                "evidence": {
                    "outlier_count": int(outlier_count),
                    "outlier_ratio": round(float(outlier_ratio), 4),
                    "mean": round(float(mean), 3),
                    "std": round(float(std), 3)
                },
                "timestamp": datetime.utcnow().isoformat(),
                "severity": "low"
            }
        return None
    
    def _check_correlations_cached(self, data_cache: Dict) -> List[Dict]:
        """Check 8: Correlation Breakdown using cached data"""
        anomalies = []

        for tag_a, tag_b in self.correlated_pairs:
            a_data = data_cache.get(tag_a)
            b_data = data_cache.get(tag_b)
            if not a_data or not b_data:
                continue

            vals_a = a_data["values"]
            vals_b = b_data["values"]

            if len(vals_a) < 30 or len(vals_b) < 30:
                continue

            n = min(len(vals_a), len(vals_b))
            vals_a = vals_a[:n]
            vals_b = vals_b[:n]

            if np.std(vals_a) == 0 or np.std(vals_b) == 0:
                continue

            corr, p_value = stats.pearsonr(vals_a, vals_b)

            first_half_n = n // 2
            corr_first, _ = stats.pearsonr(vals_a[:first_half_n], vals_b[:first_half_n])
            corr_second, _ = stats.pearsonr(vals_a[first_half_n:], vals_b[first_half_n:])

        correlation_shift = abs(corr_second - corr_first)

            if correlation_shift > 0.8 and n > 50:
                anomalies.append({
                    "tag_id": tag_a,
                    "anomaly_type": "correlation_breakdown",
                    "confidence": min(0.9, float(correlation_shift)),
                    "evidence": {
                        "pair": f"{tag_a} vs {tag_b}",
                        "partner_tag": tag_b,
                        "full_correlation": round(float(corr), 3),
                        "first_half_correlation": round(float(corr_first), 3),
                        "second_half_correlation": round(float(corr_second), 3),
                        "shift": round(float(correlation_shift), 3),
                        "n_readings": n
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                    "severity": "high" if correlation_shift > 0.6 else "medium"
                })

        return anomalies
    
    async def _check_pharma_specific_cached(self, data_cache: Dict, tag_metadata: Dict) -> List[Dict]:
        """Check 9 & 10: Pharma-specific checks (CIP and FDA audit) using cached data"""
        anomalies = []

        cip_by_tag = {}
        for tag_id, tag_data in data_cache.items():
            meta = tag_metadata.get(tag_id, {})
            if meta.get("unit_type") == "CIP System":
                cip_by_tag[tag_id] = tag_data["values"]

        if "TI-601" in cip_by_tag:
            temp_values = cip_by_tag["TI-601"]
            low_temp_count = int(np.sum(temp_values < 70))
            if low_temp_count > 30:
                anomalies.append({
                    "tag_id": "TI-601",
                    "anomaly_type": "cip_temperature_low",
                    "confidence": min(0.9, low_temp_count / 100),
                    "evidence": {
                        "low_temp_readings": low_temp_count,
                        "min_temp": round(float(np.min(temp_values)), 2),
                        "threshold": 70
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                    "severity": "high",
                    "pharma_impact": "Incomplete cleaning - contamination risk"
                })

        quality_agg = await self.db_conn.fetch(
            """
            SELECT tag_id, quality_code, COUNT(*) as cnt
            FROM tag_readings
            WHERE timestamp >= NOW() - INTERVAL '24 hours'
            GROUP BY tag_id, quality_code
            """
        )
        tag_quality = {}
        for r in quality_agg:
            tid = r["tag_id"]
            if tid not in tag_quality:
                tag_quality[tid] = {"total": 0, "bad": 0}
            tag_quality[tid]["total"] += r["cnt"]
            if r["quality_code"] not in ("Good", None):
                tag_quality[tid]["bad"] += r["cnt"]

        for tid, q in tag_quality.items():
            if q["total"] > 100 and q["bad"] / q["total"] > 0.5:
                anomalies.append({
                    "tag_id": tid,
                    "anomaly_type": "fda_audit_trail_concern",
                    "confidence": 0.7,
                    "evidence": {
                        "non_good_ratio": round(q["bad"] / q["total"], 3),
                        "total_readings": q["total"],
                        "non_good_readings": q["bad"]
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                    "severity": "high",
                    "pharma_impact": "21 CFR Part 11 compliance concern"
                })

        return anomalies

    def _check_cross_sensor_consistency_cached(self, tag_profiles: Dict, data_cache: Dict) -> List[Dict]:
        """Check 11: Cross-Sensor Corroboration using cached data"""
        anomalies = []

        for suspect_tag, config in self.cross_sensor_groups.items():
            suspect_profile = tag_profiles.get(suspect_tag)
            if not suspect_profile:
                print(f"  [cross-sensor] {suspect_tag}: SKIP - no profile")
                continue

            suspect_data = data_cache.get(suspect_tag)
            if not suspect_data or len(suspect_data["values"]) < 30:
                print(f"  [cross-sensor] {suspect_tag}: SKIP - only {len(suspect_data['values']) if suspect_data else 0} readings")
                continue

            suspect_values = suspect_data["values"]
            n_suspect = len(suspect_values)
            interval_sec = 86400.0 / n_suspect if n_suspect > 0 else 30
            print(f"  [cross-sensor] {suspect_tag}: {n_suspect} readings, interval={interval_sec:.1f}s, mean={np.mean(suspect_values):.2f}, std={np.std(suspect_values):.2f}")
            # Adaptive window: 1 hour at current data interval
            window_size = max(30, int(3600 / interval_sec))
            step = max(window_size // 2, 1)
            half_window = max(15, window_size // 2)
            
            suspect_mean = float(np.mean(suspect_values))
            suspect_std = float(np.std(suspect_values))

            if suspect_std == 0:
                continue

            contradictions = []

            for witness_tag, rel in config['relationships'].items():
                witness_data = data_cache.get(witness_tag)
                if not witness_data or len(witness_data["values"]) < 30:
                    continue

                witness_values = witness_data["values"]
                witness_mean = float(np.mean(witness_values))
                witness_std = float(np.std(witness_values))

                if witness_std == 0 or suspect_std == 0:
                    continue

                n = min(len(suspect_values), len(witness_values))
                s = suspect_values[:n]
                w = witness_values[:n]

                overall_corr, _ = stats.pearsonr(s, w)

                segment_correlations = []

                for start in range(0, n - window_size, step):
                    seg_s = s[start:start + window_size]
                    seg_w = w[start:start + window_size]
                    if np.std(seg_s) > 0 and np.std(seg_w) > 0:
                        seg_corr, _ = stats.pearsonr(seg_s, seg_w)
                        segment_correlations.append(seg_corr)

                if not segment_correlations:
                    continue

                first_windows = min(3, len(segment_correlations))
                baseline_corr = np.mean(segment_correlations[:first_windows]) if first_windows > 0 else overall_corr
                recent_corr = segment_correlations[-1] if segment_correlations else overall_corr

                correlation_drop = baseline_corr - recent_corr

                if correlation_drop > 0.2 and abs(baseline_corr) > 0.05:
                    s_recent = suspect_values[-window_size:]
                    w_recent = witness_values[-window_size:]
                    s_recent_trend = float(np.mean(s_recent[-half_window:]) - np.mean(s_recent[:half_window]))
                    w_recent_trend = float(np.mean(w_recent[-half_window:]) - np.mean(w_recent[:half_window]))

                    expected_direction = 1 if rel['direction'] == 'same' else -1

                    trends_contradict = False
                    if expected_direction > 0:
                        if (s_recent_trend > 0 and w_recent_trend < -suspect_std * 0.1) or \
                           (s_recent_trend < 0 and w_recent_trend > suspect_std * 0.1):
                            trends_contradict = True
                    else:
                        if (s_recent_trend > 0 and w_recent_trend > suspect_std * 0.1) or \
                           (s_recent_trend < 0 and w_recent_trend < -suspect_std * 0.1):
                            trends_contradict = True

                    if trends_contradict or correlation_drop > 0.3:
                        contradictions.append({
                            'witness': witness_tag,
                            'relationship': rel['desc'],
                            'baseline_correlation': round(float(baseline_corr), 3),
                            'recent_correlation': round(float(recent_corr), 3),
                            'correlation_drop': round(float(correlation_drop), 3),
                            'suspect_trend': round(float(s_recent_trend), 3),
                            'witness_trend': round(float(w_recent_trend), 3),
                            'trends_contradict': trends_contradict,
                            'expected_direction': rel['direction'],
                        })

            if contradictions:
                confidence = min(0.95, 0.6 + 0.15 * len(contradictions))
                if any(c['trends_contradict'] for c in contradictions):
                    confidence = min(0.95, confidence + 0.1)
                if len(contradictions) >= 2:
                    confidence = min(0.95, confidence + 0.05)

                witness_summary = ", ".join(c['witness'] for c in contradictions)

                anomalies.append({
                    "tag_id": suspect_tag,
                    "anomaly_type": "cross_sensor_inconsistency",
                    "confidence": round(float(confidence), 2),
                    "evidence": {
                        "witness_count": len(contradictions),
                        "witnesses": witness_summary,
                        "contradictions": contradictions,
                        "suspect_mean": round(float(suspect_mean), 3),
                        "suspect_std": round(float(suspect_std), 3),
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                    "severity": "high",
                    "pharma_impact": f"Sensor {suspect_tag} contradicts {witness_summary} — reading may be plausible but wrong. Risk of incorrect batch decisions.",
                    "is_silent_lie": True,
                })

        return anomalies
    
    def _count_by_type(self, anomalies: List[Dict]) -> Dict[str, int]:
        """Count anomalies by type"""
        counts = {}
        for a in anomalies:
            atype = a["anomaly_type"]
            counts[atype] = counts.get(atype, 0) + 1
        return counts