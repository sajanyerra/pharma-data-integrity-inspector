"""
Pharma Tag Simulator
Generates realistic sensor data for 20 pharma process tags with:
- Cross-tag causal correlations (physics-based coupling)
- Autocorrelation (AR(1) model for temporal smoothness)
- Injected anomalies: sensor drift, stuck value, and SILENT LIE
"""

import random
import math
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional


class TagSimulator:
    
    TAG_CONFIGS = {
        'TI-101': {'base': 175, 'noise': 2.0, 'unit': 'deg_C', 'data_type': 'Temperature'},
        'PI-101': {'base': 3.5, 'noise': 0.3, 'unit': 'bar', 'data_type': 'Pressure'},
        'FI-101': {'base': 300, 'noise': 15, 'unit': 'L_min', 'data_type': 'Flow'},
        'LI-101': {'base': 55, 'noise': 3, 'unit': 'pct', 'data_type': 'Level'},
        'TI-201': {'base': 60, 'noise': 2, 'unit': 'deg_C', 'data_type': 'Temperature'},
        'FI-201': {'base': 500, 'noise': 30, 'unit': 'L_min', 'data_type': 'Flow'},
        'TI-202': {'base': 80, 'noise': 3, 'unit': 'deg_C', 'data_type': 'Temperature'},
        'PI-301': {'base': 5.5, 'noise': 0.4, 'unit': 'bar', 'data_type': 'Pressure'},
        'FI-301': {'base': 250, 'noise': 20, 'unit': 'L_min', 'data_type': 'Flow'},
        'VI-301': {'base': 4.2, 'noise': 0.5, 'unit': 'mm_s', 'data_type': 'Vibration'},
        'TI-401': {'base': 30, 'noise': 1, 'unit': 'deg_C', 'data_type': 'Temperature'},
        'LI-401': {'base': 50, 'noise': 5, 'unit': 'pct', 'data_type': 'Level'},
        'PI-401': {'base': 1.2, 'noise': 0.1, 'unit': 'bar', 'data_type': 'Pressure'},
        'TI-501': {'base': 115, 'noise': 5, 'unit': 'deg_C', 'data_type': 'Temperature'},
        'PI-501': {'base': 2, 'noise': 0.2, 'unit': 'bar', 'data_type': 'Pressure'},
        'PI-502': {'base': 8, 'noise': 0.5, 'unit': 'bar', 'data_type': 'Pressure'},
        'TI-601': {'base': 77.5, 'noise': 2, 'unit': 'deg_C', 'data_type': 'Temperature'},
        'FI-601': {'base': 1000, 'noise': 50, 'unit': 'L_min', 'data_type': 'Flow'},
        'CI-601': {'base': 30, 'noise': 2, 'unit': 'mS_cm', 'data_type': 'Conductivity'},
        'AI-901': {'base': 20, 'noise': 1.5, 'unit': 'Pa', 'data_type': 'Pressure'},
    }

    CAUSAL_GROUPS = {
        'Reactor R-101': {
            'tags': ['TI-101', 'PI-101', 'FI-101', 'LI-101'],
            'couplings': {
                'TI-101->PI-101': {
                    'coeff': 0.05,
                    'desc': 'Clausius-Clapeyron: higher reactor temp -> higher vapor pressure',
                },
                'FI-101->LI-101': {
                    'coeff': 0.15,
                    'desc': 'Feed flow raises reactor level over time',
                },
                'TI-101->FI-201': {
                    'coeff': -0.8,
                    'desc': 'Higher reactor temp -> cooling system compensates with more flow',
                },
            },
        },
        'HX-201': {
            'tags': ['TI-201', 'FI-201', 'TI-202'],
            'couplings': {
                'TI-201->TI-202': {
                    'coeff': 0.9,
                    'desc': 'Cold side outlet tracks hot side inlet via heat transfer',
                },
                'FI-201->TI-202': {
                    'coeff': -0.01,
                    'desc': 'More cooling water -> lower HX outlet temp',
                },
            },
        },
        'Pump P-301': {
            'tags': ['PI-301', 'FI-301', 'VI-301'],
            'couplings': {
                'PI-301->FI-301': {
                    'coeff': 20.0,
                    'desc': 'Pump curve: higher discharge pressure relates to flow',
                },
                'FI-301->VI-301': {
                    'coeff': 0.01,
                    'desc': 'Vibration increases with flow rate',
                },
            },
        },
        'Comp C-501': {
            'tags': ['TI-501', 'PI-501', 'PI-502'],
            'couplings': {
                'PI-501->PI-502': {
                    'coeff': 3.0,
                    'desc': 'Compressor ratio: suction pressure drives discharge',
                },
                'PI-501->TI-501': {
                    'coeff': 25.0,
                    'desc': 'Compression: higher suction pressure -> higher discharge temp',
                },
            },
        },
        'CIP System': {
            'tags': ['TI-601', 'FI-601', 'CI-601'],
            'couplings': {
                'FI-601->TI-601': {
                    'coeff': 0.005,
                    'desc': 'Higher CIP flow -> better heat delivery -> higher supply temp',
                },
                'TI-601->CI-601': {
                    'coeff': 0.5,
                    'desc': 'Higher CIP temp improves chemical effectiveness (conductivity proxy)',
                },
            },
        },
    }

    CROSS_GROUP_COUPLINGS = {
        'TI-101->FI-201': {
            'coeff': -0.8,
            'desc': 'Reactor temp rise -> cooling system compensates',
            'source_group': 'Reactor R-101',
            'target_group': 'HX-201',
        },
        'LI-101->FI-301': {
            'coeff': 3.0,
            'desc': 'Reactor level drives pump demand',
            'source_group': 'Reactor R-101',
            'target_group': 'Pump P-301',
        },
    }

    CORRELATED_PAIRS = [
        ('FI-101', 'LI-101'),
        ('TI-201', 'TI-202'),
        ('PI-501', 'PI-502'),
        ('TI-601', 'FI-601'),
        ('TI-101', 'PI-101'),
        ('PI-301', 'FI-301'),
        ('VI-301', 'FI-301'),
    ]

    ANOMALIES = {
        'TI-101': {
            'type': 'sensor_drift',
            'start_hour': 14,
            'start_minute': 32,
            'duration_hours': 18,
            'drift_rate': 2.5,
        },
        'VI-301': {
            'type': 'stuck_value',
            'start_hour': 3,
            'start_minute': 15,
            'duration_hours': 6,
            'stuck_value': 4.2,
        },
    }

    SILENT_LIE = {
        'tag_id': 'TI-101',
        'type': 'silent_lie',
        'start_hour': 10,
        'start_minute': 0,
        'duration_hours': 4,
        'offset': -3.0,
        'desc': 'TI-101 miscalibrated: reports 3 deg C LOW. Correlated sensors (PI-101, FI-201, LI-101) contradict the reading.',
    }

    def __init__(self, seed: int = None):
        if seed is not None:
            random.seed(seed)
        self.start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self._prev_values: Dict[str, float] = {}
        self._deviations: Dict[str, float] = {}
        self.ar_coeff = 0.85

    def _get_noise(self, noise_level: float) -> float:
        return random.gauss(0, noise_level)

    def _compute_causal_deviations(self, timestamp: datetime) -> Dict[str, float]:
        raw_deviations = {}
        for group_name, group in self.CAUSAL_GROUPS.items():
            for coupling_key, coupling in group['couplings'].items():
                source_tag, target_tag = coupling_key.split('->')
                if source_tag in self._prev_values:
                    source_dev = self._prev_values[source_tag] - self.TAG_CONFIGS[source_tag]['base']
                    base_deviation = raw_deviations.get(target_tag, 0.0)
                    raw_deviations[target_tag] = base_deviation + source_dev * coupling['coeff']

        for coupling_key, coupling in self.CROSS_GROUP_COUPLINGS.items():
            source_tag, target_tag = coupling_key.split('->')
            if source_tag in self._prev_values:
                source_dev = self._prev_values[source_tag] - self.TAG_CONFIGS[source_tag]['base']
                base_deviation = raw_deviations.get(target_tag, 0.0)
                raw_deviations[target_tag] = base_deviation + source_dev * coupling['coeff']

        deviations = {}
        for tag_id, dev in raw_deviations.items():
            config = self.TAG_CONFIGS.get(tag_id)
            if not config:
                deviations[tag_id] = dev
                continue
            max_dev = abs(config['base'] - config['normal_min']) if config.get('normal_min') else abs(config['base'] * 0.3)
            max_allowed = max(max_dev, config['noise'] * 10)
            deviations[tag_id] = max(-max_allowed, min(max_allowed, dev))

        return deviations

    def _calculate_drift(self, tag_id: str, current_time: datetime) -> float:
        if tag_id not in self.ANOMALIES:
            return 0.0
        anomaly = self.ANOMALIES[tag_id]
        if anomaly['type'] != 'sensor_drift':
            return 0.0
        anomaly_start = self.start_time.replace(hour=anomaly['start_hour'], minute=anomaly['start_minute'])
        anomaly_end = anomaly_start + timedelta(hours=anomaly['duration_hours'])
        if anomaly_start <= current_time <= anomaly_end:
            hours_elapsed = (current_time - anomaly_start).total_seconds() / 3600
            return hours_elapsed * anomaly['drift_rate']
        return 0.0

    def _is_stuck(self, tag_id: str, current_time: datetime) -> tuple:
        if tag_id not in self.ANOMALIES:
            return False, 0.0
        anomaly = self.ANOMALIES[tag_id]
        if anomaly['type'] != 'stuck_value':
            return False, 0.0
        anomaly_start = self.start_time.replace(hour=anomaly['start_hour'], minute=anomaly['start_minute'])
        anomaly_end = anomaly_start + timedelta(hours=anomaly['duration_hours'])
        if anomaly_start <= current_time <= anomaly_end:
            return True, anomaly['stuck_value']
        return False, 0.0

    def _get_silent_lie_offset(self, tag_id: str, current_time: datetime) -> float:
        if self.SILENT_LIE['tag_id'] != tag_id:
            return 0.0
        lie = self.SILENT_LIE
        anomaly_start = self.start_time.replace(hour=lie['start_hour'], minute=lie['start_minute'])
        anomaly_end = anomaly_start + timedelta(hours=lie['duration_hours'])
        if anomaly_start <= current_time <= anomaly_end:
            return lie['offset']
        return 0.0

    def _is_silent_lie_active(self, current_time: datetime) -> bool:
        lie = self.SILENT_LIE
        anomaly_start = self.start_time.replace(hour=lie['start_hour'], minute=lie['start_minute'])
        anomaly_end = anomaly_start + timedelta(hours=lie['duration_hours'])
        return anomaly_start <= current_time <= anomaly_end

    def generate_value(self, tag_id: str, timestamp: datetime) -> Dict[str, Any]:
        if tag_id not in self.TAG_CONFIGS:
            raise ValueError(f"Unknown tag: {tag_id}")
        config = self.TAG_CONFIGS[tag_id]

        is_stuck, stuck_value = self._is_stuck(tag_id, timestamp)
        if is_stuck:
            self._prev_values[tag_id] = stuck_value
            return {
                'tag_id': tag_id,
                'timestamp': timestamp,
                'value': stuck_value,
                'quality_code': 'Good',
                'unit': config['unit'],
                'is_anomaly': True,
                'anomaly_type': 'stuck_value'
            }

        noise = self._get_noise(config['noise'])
        causal_dev = self._deviations.get(tag_id, 0.0)
        hour_variation = math.sin(2 * math.pi * timestamp.hour / 24) * config['noise'] * 0.3

        prev = self._prev_values.get(tag_id, config['base'])
        natural_value = config['base'] + causal_dev + hour_variation + noise
        true_value = self.ar_coeff * prev + (1 - self.ar_coeff) * natural_value

        drift = self._calculate_drift(tag_id, timestamp)
        if drift != 0:
            true_value += drift

        self._prev_values[tag_id] = true_value

        reported_value = round(true_value, 3)

        silent_lie_offset = self._get_silent_lie_offset(tag_id, timestamp)
        if silent_lie_offset != 0:
            reported_value = round(true_value + silent_lie_offset, 3)

        quality_code = 'Good'
        if random.random() < 0.02:
            quality_code = 'Warning'
        if random.random() < 0.005:
            quality_code = 'Bad'

        is_anomaly = drift != 0 or silent_lie_offset != 0
        anomaly_type = None
        if drift != 0:
            anomaly_type = 'sensor_drift'
        elif silent_lie_offset != 0:
            anomaly_type = 'silent_lie'

        return {
            'tag_id': tag_id,
            'timestamp': timestamp,
            'value': reported_value,
            'quality_code': quality_code,
            'unit': config['unit'],
            'is_anomaly': is_anomaly,
            'anomaly_type': anomaly_type
        }

    def generate_all_tags(self, timestamp: datetime) -> List[Dict[str, Any]]:
        self._deviations = self._compute_causal_deviations(timestamp)
        results = []
        for tag_id in self.TAG_CONFIGS.keys():
            results.append(self.generate_value(tag_id, timestamp))
        return results

    def get_tag_metadata(self) -> List[Dict[str, Any]]:
        tag_info = {
            'TI-101': ('Reactor Temp', 'Reactor R-101', 'Temperature', 150, 200, 'Exothermic reaction temperature'),
            'PI-101': ('Reactor Pressure', 'Reactor R-101', 'Pressure', 2, 5, 'Reactor headspace pressure'),
            'FI-101': ('Feed Flow', 'Reactor R-101', 'Flow', 100, 500, 'Raw material feed rate'),
            'LI-101': ('Reactor Level', 'Reactor R-101', 'Level', 30, 80, 'Liquid level in reactor'),
            'TI-201': ('Heat Exchanger Outlet', 'HX-201', 'Temperature', 40, 80, 'Product cooling temperature'),
            'FI-201': ('Cooling Water Flow', 'HX-201', 'Flow', 200, 800, 'Product cooling water flow'),
            'TI-202': ('HX Hot Side Outlet', 'HX-201', 'Temperature', 60, 100, 'Process side outlet temp'),
            'PI-301': ('Pump Discharge Pressure', 'Pump P-301', 'Pressure', 3, 8, 'Centrifugal pump discharge'),
            'FI-301': ('Pump Flow', 'Pump P-301', 'Flow', 100, 400, 'Pump flow rate'),
            'VI-301': ('Pump Vibration', 'Pump P-301', 'Vibration', 0, 10, 'Bearing vibration monitoring'),
            'TI-401': ('Tank Temperature', 'Tank T-401', 'Temperature', 20, 40, 'Storage tank temperature'),
            'LI-401': ('Tank Level', 'Tank T-401', 'Level', 10, 90, 'Tank liquid level'),
            'PI-401': ('Tank Pressure', 'Tank T-401', 'Pressure', 0.5, 2, 'Tank headspace pressure'),
            'TI-501': ('Compressor Discharge', 'Comp C-501', 'Temperature', 80, 150, 'Compressor outlet temp'),
            'PI-501': ('Compressor Suction', 'Comp C-501', 'Pressure', 1, 3, 'Compressor inlet pressure'),
            'PI-502': ('Compressor Discharge', 'Comp C-501', 'Pressure', 6, 10, 'Compressor outlet pressure'),
            'TI-601': ('CIP Supply Temp', 'CIP System', 'Temperature', 70, 85, 'Clean-in-place supply temp'),
            'FI-601': ('CIP Flow Rate', 'CIP System', 'Flow', 500, 1500, 'CIP circulation flow'),
            'CI-601': ('CIP Concentration', 'CIP System', 'Conductivity', 10, 50, 'Caustic concentration'),
            'AI-901': ('Room Pressure', 'HVAC', 'Pressure', 10, 30, 'Cleanroom differential pressure'),
        }
        metadata = []
        for tag_id, (name, unit_type, data_type, min_val, max_val, desc) in tag_info.items():
            metadata.append({
                'tag_id': tag_id,
                'tag_name': name,
                'unit_type': unit_type,
                'data_type': data_type,
                'normal_min': min_val,
                'normal_max': max_val,
                'scan_rate_sec': 5,
                'description': desc
            })
        return metadata

    def get_causal_groups(self) -> Dict:
        result = {}
        for group_name, group in self.CAUSAL_GROUPS.items():
            result[group_name] = {
                'tags': group['tags'],
                'couplings': {}
            }
            for coupling_key, coupling in group['couplings'].items():
                result[group_name]['couplings'][coupling_key] = {
                    'coeff': coupling['coeff'],
                    'desc': coupling['desc']
                }
        result['_cross_group'] = {}
        for coupling_key, coupling in self.CROSS_GROUP_COUPLINGS.items():
            result['_cross_group'][coupling_key] = {
                'coeff': coupling['coeff'],
                'desc': coupling['desc'],
                'source_group': coupling['source_group'],
                'target_group': coupling['target_group'],
            }
        return result

    def get_silent_lie_config(self) -> Dict:
        return dict(self.SILENT_LIE)


if __name__ == '__main__':
    simulator = TagSimulator(seed=42)

    test_time = datetime.now()
    readings = simulator.generate_all_tags(test_time)
    print(f"Generated {len(readings)} tag readings at {test_time}")
    for reading in readings[:5]:
        print(f"  {reading['tag_id']}: {reading['value']} {reading['unit']} ({reading['quality_code']})")

    lie_time = datetime.now().replace(hour=11, minute=0)
    simulator2 = TagSimulator(seed=42)
    readings2 = simulator2.generate_all_tags(lie_time)
    print(f"\nAt {lie_time} (silent lie active for TI-101):")
    for r in readings2:
        if r['tag_id'] in ['TI-101', 'PI-101', 'FI-201', 'LI-101']:
            print(f"  {r['tag_id']}: {r['value']} {r['unit']} (anomaly: {r.get('anomaly_type', 'none')})")

    print(f"\nSilent lie config: {simulator.get_silent_lie_config()}")
    print(f"Causal groups: {list(simulator.get_causal_groups().keys())}")