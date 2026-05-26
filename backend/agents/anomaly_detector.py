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
    """Detects data integrity anomalies using 11 detection algorithms with AI prioritization"""
    
    def __init__(self):
        super().__init__("AnomalyDetector")
        self.llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0.2,
            openai_api_key=settings.OPENAI_API_KEY
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
        
        self.cross_sensor_groups = {
            'TI-101': {
                'witnesses': ['PI-101', 'FI-201', 'LI-101'],
                'relationships': {
                    'PI-101': {'coeff': 0.05, 'direction': 'same', 'desc': 'Higher reactor temp -> higher vapor pressure (Clausius-Clapeyron)'},
                    'FI-201': {'coeff': -0.8, 'direction': 'opposite', 'desc': 'Higher reactor temp -> cooling system increases flow'},
                    'LI-101': {'coeff': 0.15, 'direction': 'same', 'desc': 'Temperature affects reaction rate which changes feed consumption'},
                },
            },
            'VI-301': {
                'witnesses': ['PI-301', 'FI-301'],
                'relationships': {
                    'PI-301': {'coeff': 0.08, 'direction': 'same', 'desc': 'Higher pump pressure -> more vibration'},
                    'FI-301': {'coeff': 0.01, 'direction': 'same', 'desc': 'Higher flow -> more vibration'},
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
        
    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply 11 anomaly detection checks
        
        Input: {
            "tag_profiles": Dict from DataProfiler,
            "hours": int (default 24)
        }
        
        Output: {
            "anomalies": List[anomaly_dict],
            "summary": {...}
        }
        """
        await self.connect_db()
        
        try:
            tag_profiles = input_data.get("tag_profiles", {})
            hours = input_data.get("hours", 24)
            anomalies = []
            
            tags_result = await self.db_conn.fetch("SELECT * FROM tags")
            tag_metadata = {row["tag_id"]: dict(row) for row in tags_result}
            
            for tag_id, profile in tag_profiles.items():
                metadata = tag_metadata.get(tag_id, {})
                data_type = metadata.get("data_type", "Unknown")
                
                cutoff_time = datetime.utcnow() - timedelta(hours=hours)
                readings = await self.db_conn.fetch(
                    "SELECT value, quality_code, timestamp FROM tag_readings WHERE tag_id = $1 AND timestamp >= $2 ORDER BY timestamp",
                    tag_id, cutoff_time
                )
                values = [float(r["value"]) for r in readings if r["value"] is not None]
                
                if len(values) < 10:
                    continue
                
                values_array = np.array(values)
                
                drift_anomaly = self._check_sensor_drift(tag_id, values_array, profile)
                if drift_anomaly:
                    anomalies.append(drift_anomaly)
                
                stuck_anomaly = self._check_stuck_value(tag_id, values_array, readings)
                if stuck_anomaly:
                    anomalies.append(stuck_anomaly)
                
                impossible_anomaly = self._check_impossible_readings(tag_id, values_array, data_type)
                if impossible_anomaly:
                    anomalies.append(impossible_anomaly)
                
                quality_anomaly = self._check_quality_mismatch(tag_id, values_array, profile)
                if quality_anomaly:
                    anomalies.append(quality_anomaly)
                
                roc_anomaly = self._check_rate_of_change(tag_id, values_array, readings, data_type)
                if roc_anomaly:
                    anomalies.append(roc_anomaly)
                
                gap_anomaly = self._check_data_gaps(tag_id, readings)
                if gap_anomaly:
                    anomalies.append(gap_anomaly)
                
                outlier_anomaly = self._check_statistical_outliers(tag_id, values_array, profile)
                if outlier_anomaly:
                    anomalies.append(outlier_anomaly)
            
            correlation_anomalies = await self._check_correlations(cutoff_time)
            anomalies.extend(correlation_anomalies)
            
            pharma_anomalies = await self._check_pharma_specific(cutoff_time)
            anomalies.extend(pharma_anomalies)
            
            silent_lie_anomalies = await self._check_cross_sensor_consistency(tag_profiles, cutoff_time)
            anomalies.extend(silent_lie_anomalies)
            
            result = {
                "anomalies": anomalies,
                "summary": {
                    "total_anomalies": len(anomalies),
                    "by_type": self._count_by_type(anomalies),
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            
            result["ai_prioritization"] = await self._prioritize_anomalies(anomalies)
            
            await self.save_trace(input_data, result)
            return result
            
        finally:
            await self.disconnect_db()
    
    async def _prioritize_anomalies(self, anomalies: List) -> str:
        """Use LLM to analyze detection patterns and explain pharma implications"""
        if not anomalies:
            return "No anomalies detected. All sensor data appears within normal parameters."
        
        prompt = PromptTemplate(
            template="""You are a pharma process engineer reviewing integrity check results from a pharmaceutical plant. These anomalies were detected by the rule engine. Your job: analyze the PATTERN of findings and explain what they mean together.

Detected anomalies (from 11 checks: sensor drift, stuck values, impossible readings, rate-of-change, quality code mismatch, data gaps, statistical outliers, correlation breakdown, CIP issues, FDA audit trail, CROSS-SENSOR CONSISTENCY/SILENT LIE):
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
        """Check 1: Sensor Drift - Compare 1h vs 6h rolling mean"""
        if len(values) < 720:
            return None
        
        recent_1h = values[-720:]
        previous_6h = values[-4320:-720]
        
        if len(previous_6h) < 100:
            return None
            
        recent_mean = np.mean(recent_1h)
        previous_mean = np.mean(previous_6h)
        
        deviation = abs(recent_mean - previous_mean) / (abs(previous_mean) + 0.001) * 100
        drift_rate = deviation / 6
        
        if drift_rate > 3.5:
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
        """Check 2: Stuck Value - Scan full period with 1h windows"""
        if len(values) < 720:
            return None
        
        window_size = 720
        step = window_size
        for start in range(0, len(values) - window_size + 1, step):
            window = values[start:start + window_size]
            unique_values = len(np.unique(window))
            if unique_values < 3:
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
        if len(values) < 100:
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
        
        if violation_count > 5:
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
    
    def _check_data_gaps(self, tag_id: str, readings: List) -> Dict:
        """Check 6: Data Gaps - Gap > 2x scan rate (10 sec)"""
        if len(readings) < 2:
            return None
        
        gaps = []
        for i in range(1, len(readings)):
            time_diff = (readings[i]["timestamp"] - readings[i-1]["timestamp"]).total_seconds()
            if time_diff > 10:
                gaps.append(time_diff)
        
        if gaps:
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
    
    async def _check_correlations(self, cutoff_time: datetime) -> List[Dict]:
        """Check 8: Correlation Breakdown between related tags"""
        anomalies = []
        
        for tag_a, tag_b in self.correlated_pairs:
            readings_a = await self.db_conn.fetch(
                "SELECT value, timestamp FROM tag_readings WHERE tag_id = $1 AND timestamp >= $2 ORDER BY timestamp",
                tag_a, cutoff_time
            )
            readings_b = await self.db_conn.fetch(
                "SELECT value, timestamp FROM tag_readings WHERE tag_id = $1 AND timestamp >= $2 ORDER BY timestamp",
                tag_b, cutoff_time
            )
            
            if len(readings_a) < 100 or len(readings_b) < 100:
                continue
            
            vals_a = np.array([float(r["value"]) for r in readings_a])
            vals_b = np.array([float(r["value"]) for r in readings_b])
            
            n = min(len(vals_a), len(vals_b))
            vals_a = vals_a[:n]
            vals_b = vals_b[:n]
            
            if np.std(vals_a) == 0 or np.std(vals_b) == 0:
                continue
            
            corr, p_value = stats.pearsonr(vals_a, vals_b)
            
            first_half_n = n // 2
            second_half_n = n - first_half_n
            corr_first, _ = stats.pearsonr(vals_a[:first_half_n], vals_b[:first_half_n])
            corr_second, _ = stats.pearsonr(vals_a[first_half_n:], vals_b[first_half_n:])
            
            correlation_shift = abs(corr_second - corr_first)
            
            if correlation_shift > 0.6 and n > 200:
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
    
    async def _check_pharma_specific(self, cutoff_time: datetime) -> List[Dict]:
        """Check 9 & 10: Pharma-specific checks (CIP and FDA audit)"""
        anomalies = []
        
        cip_readings = await self.db_conn.fetch(
            """
            SELECT tr.tag_id, tr.value, tr.timestamp
            FROM tag_readings tr
            JOIN tags t ON tr.tag_id = t.tag_id
            WHERE t.unit_type = 'CIP System' AND tr.timestamp >= $1
            ORDER BY tr.timestamp
            """,
            cutoff_time
        )
        
        cip_by_tag = {}
        for r in cip_readings:
            if r["tag_id"] not in cip_by_tag:
                cip_by_tag[r["tag_id"]] = []
            cip_by_tag[r["tag_id"]].append(float(r["value"]))
        
        if "TI-601" in cip_by_tag:
            temp_values = cip_by_tag["TI-601"]
            low_temp_count = sum(1 for v in temp_values if v < 70)
            if low_temp_count > 10:
                anomalies.append({
                    "tag_id": "TI-601",
                    "anomaly_type": "cip_temperature_low",
                    "confidence": min(0.9, low_temp_count / 100),
                    "evidence": {
                        "low_temp_readings": low_temp_count,
                        "min_temp": round(min(temp_values), 2),
                        "threshold": 70
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                    "severity": "high",
                    "pharma_impact": "Incomplete cleaning - contamination risk"
                })
        
        tags_result = await self.db_conn.fetch("SELECT tag_id FROM tags")
        for tag_row in tags_result:
            tag_id = tag_row["tag_id"]
            quality_changes = await self.db_conn.fetch(
                """
                SELECT quality_code, COUNT(*) as cnt
                FROM tag_readings
                WHERE tag_id = $1 AND timestamp >= $2
                GROUP BY quality_code
                """,
                tag_id, cutoff_time
            )
            
            total = sum(r["cnt"] for r in quality_changes)
            bad_count = sum(r["cnt"] for r in quality_changes if r["quality_code"] not in ["Good", None])
            
            if total > 100 and bad_count / total > 0.5:
                anomalies.append({
                    "tag_id": tag_id,
                    "anomaly_type": "fda_audit_trail_concern",
                    "confidence": 0.7,
                    "evidence": {
                        "non_good_ratio": round(bad_count / total, 3),
                        "total_readings": total,
                        "non_good_readings": bad_count
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                    "severity": "high",
                    "pharma_impact": "21 CFR Part 11 compliance concern"
                })
        
        return anomalies

    async def _check_cross_sensor_consistency(self, tag_profiles: Dict, cutoff_time: datetime) -> List[Dict]:
        """Check 11: Cross-Sensor Corroboration
        
        For each suspect tag, compare its reported behavior against its
        'witness' sensors (correlated tags). If the witnesses tell a
        different story than the suspect, the suspect may be lying.
        """
        anomalies = []
        
        for suspect_tag, config in self.cross_sensor_groups.items():
            suspect_profile = tag_profiles.get(suspect_tag)
            if not suspect_profile:
                continue
            
            suspect_readings = await self.db_conn.fetch(
                "SELECT value, timestamp FROM tag_readings WHERE tag_id = $1 AND timestamp >= $2 ORDER BY timestamp",
                suspect_tag, cutoff_time
            )
            if len(suspect_readings) < 200:
                continue
            
            suspect_values = np.array([float(r["value"]) for r in suspect_readings])
            suspect_mean = float(np.mean(suspect_values))
            suspect_std = float(np.std(suspect_values))
            
            if suspect_std == 0:
                continue
            
            contradictions = []
            
            for witness_tag, rel in config['relationships'].items():
                witness_readings = await self.db_conn.fetch(
                    "SELECT value, timestamp FROM tag_readings WHERE tag_id = $1 AND timestamp >= $2 ORDER BY timestamp",
                    witness_tag, cutoff_time
                )
                if len(witness_readings) < 200:
                    continue
                
                witness_values = np.array([float(r["value"]) for r in witness_readings])
                witness_mean = float(np.mean(witness_values))
                witness_std = float(np.std(witness_values))
                
                if witness_std == 0 or suspect_std == 0:
                    continue
                
                n = min(len(suspect_values), len(witness_values))
                s = suspect_values[:n]
                w = witness_values[:n]
                
                overall_corr, _ = stats.pearsonr(s, w)
                
                window_size = 720  # 1 hour of 5-sec data
                step = 360
                segment_correlations = []
                
                for start in range(0, n - window_size, step):
                    seg_s = s[start:start + window_size]
                    seg_w = w[start:start + window_size]
                    if np.std(seg_s) > 0 and np.std(seg_w) > 0:
                        seg_corr, _ = stats.pearsonr(seg_s, seg_w)
                        segment_correlations.append(seg_corr)
                
                if not segment_correlations:
                    continue
                
                window_size_det = 720
                first_windows = min(3, len(segment_correlations))
                baseline_corr = np.mean(segment_correlations[:first_windows]) if first_windows > 0 else overall_corr
                recent_corr = segment_correlations[-1] if segment_correlations else overall_corr
                
                correlation_drop = baseline_corr - recent_corr
                
                if correlation_drop > 0.2 and abs(baseline_corr) > 0.05:
                    s_recent = suspect_values[-720:]
                    w_recent = witness_values[-720:]
                    s_recent_trend = float(np.mean(s_recent[-360:]) - np.mean(s_recent[:360]))
                    w_recent_trend = float(np.mean(w_recent[-360:]) - np.mean(w_recent[:360]))
                    
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