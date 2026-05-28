"""
Pharma Tag Simulator
Generates realistic sensor data for 20 pharma process tags with:
- Cross-tag causal correlations (physics-based coupling)
- Autocorrelation (AR(1) model for temporal smoothness)
- Randomly injected anomalies (2-4 per run from a diverse pool)
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
                'TI-101->PI-101': {'coeff': 0.05, 'desc': 'Clausius-Clapeyron: higher reactor temp -> higher vapor pressure'},
                'FI-101->LI-101': {'coeff': 0.15, 'desc': 'Feed flow raises reactor level over time'},
                'TI-101->FI-201': {'coeff': -0.8, 'desc': 'Higher reactor temp -> cooling system compensates with more flow'},
            },
        },
        'HX-201': {
            'tags': ['TI-201', 'FI-201', 'TI-202'],
            'couplings': {
                'TI-201->TI-202': {'coeff': 0.9, 'desc': 'Cold side outlet tracks hot side inlet via heat transfer'},
                'FI-201->TI-202': {'coeff': -0.01, 'desc': 'More cooling water -> lower HX outlet temp'},
            },
        },
        'Pump P-301': {
            'tags': ['PI-301', 'FI-301', 'VI-301'],
            'couplings': {
                'PI-301->FI-301': {'coeff': 20.0, 'desc': 'Pump curve: higher discharge pressure relates to flow'},
                'FI-301->VI-301': {'coeff': 0.01, 'desc': 'Vibration increases with flow rate'},
            },
        },
        'Comp C-501': {
            'tags': ['TI-501', 'PI-501', 'PI-502'],
            'couplings': {
                'PI-501->PI-502': {'coeff': 3.0, 'desc': 'Compressor ratio: suction pressure drives discharge'},
                'PI-501->TI-501': {'coeff': 25.0, 'desc': 'Compression: higher suction pressure -> higher discharge temp'},
            },
        },
        'CIP System': {
            'tags': ['TI-601', 'FI-601', 'CI-601'],
            'couplings': {
                'FI-601->TI-601': {'coeff': 0.005, 'desc': 'Higher CIP flow -> better heat delivery -> higher supply temp'},
                'TI-601->CI-601': {'coeff': 0.5, 'desc': 'Higher CIP temp improves chemical effectiveness (conductivity proxy)'},
            },
        },
    }

    CROSS_GROUP_COUPLINGS = {
        'TI-101->FI-201': {'coeff': -0.8, 'desc': 'Reactor temp rise -> cooling system compensates', 'source_group': 'Reactor R-101', 'target_group': 'HX-201'},
        'LI-101->FI-301': {'coeff': 3.0, 'desc': 'Reactor level drives pump demand', 'source_group': 'Reactor R-101', 'target_group': 'Pump P-301'},
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

    CROSS_SENSOR_WITNESSES = {
        'TI-101': {
            'witnesses': ['PI-101', 'FI-201', 'LI-101'],
            'relationships': {
                'PI-101': {'coeff': 0.05, 'direction': 'same', 'desc': 'Higher reactor temp -> higher vapor pressure (Clausius-Clapeyron)'},
                'FI-201': {'coeff': -0.8, 'direction': 'opposite', 'desc': 'Higher reactor temp -> cooling system increases flow'},
                'LI-101': {'coeff': 0.15, 'direction': 'same', 'desc': 'Temperature affects reaction rate which changes feed consumption'},
            },
        },
        'PI-101': {
            'witnesses': ['TI-101', 'FI-101'],
            'relationships': {
                'TI-101': {'coeff': 0.05, 'direction': 'same', 'desc': 'Clausius-Clapeyron: higher temp -> higher pressure'},
                'FI-101': {'coeff': 0.5, 'direction': 'same', 'desc': 'Higher feed flow -> higher reactor pressure'},
            },
        },
        'FI-201': {
            'witnesses': ['TI-101', 'TI-202'],
            'relationships': {
                'TI-101': {'coeff': -0.8, 'direction': 'opposite', 'desc': 'Higher reactor temp -> more cooling flow needed'},
                'TI-202': {'coeff': -0.01, 'direction': 'opposite', 'desc': 'More cooling water -> lower HX outlet temp'},
            },
        },
        'VI-301': {
            'witnesses': ['PI-301', 'FI-301'],
            'relationships': {
                'PI-301': {'coeff': 0.08, 'direction': 'same', 'desc': 'Higher pump pressure -> more vibration'},
                'FI-301': {'coeff': 0.01, 'direction': 'same', 'desc': 'Higher flow -> more vibration'},
            },
        },
        'TI-202': {
            'witnesses': ['TI-201', 'FI-201'],
            'relationships': {
                'TI-201': {'coeff': 0.9, 'direction': 'same', 'desc': 'HX outlet tracks inlet via heat transfer'},
                'FI-201': {'coeff': -0.01, 'direction': 'opposite', 'desc': 'More cooling flow -> lower outlet temp'},
            },
        },
        'PI-502': {
            'witnesses': ['PI-501', 'TI-501'],
            'relationships': {
                'PI-501': {'coeff': 3.0, 'direction': 'same', 'desc': 'Discharge pressure tracks suction via compressor ratio'},
                'TI-501': {'coeff': 0.1, 'direction': 'same', 'desc': 'Higher compression -> higher discharge temp'},
            },
        },
        'LI-101': {
            'witnesses': ['FI-101', 'TI-101'],
            'relationships': {
                'FI-101': {'coeff': 0.15, 'direction': 'same', 'desc': 'Feed flow raises reactor level'},
                'TI-101': {'coeff': 0.02, 'direction': 'same', 'desc': 'Temperature affects density and apparent level'},
            },
        },
        'TI-601': {
            'witnesses': ['FI-601', 'CI-601'],
            'relationships': {
                'FI-601': {'coeff': 0.005, 'direction': 'same', 'desc': 'Higher CIP flow -> higher supply temp'},
                'CI-601': {'coeff': 0.5, 'direction': 'same', 'desc': 'Higher temp -> higher conductivity'},
            },
        },
    }

    ANOMALY_TEMPLATES = [
        {'type': 'sensor_drift', 'tags': ['TI-101', 'PI-101', 'FI-101', 'TI-201', 'TI-202', 'TI-401', 'TI-501', 'TI-601', 'PI-301'], 'params': {'drift_rate_range': (1.0, 5.0)}},
        {'type': 'stuck_value', 'tags': ['VI-301', 'PI-401', 'FI-301', 'FI-101', 'FI-201', 'LI-101', 'AI-901', 'CI-601'], 'params': {'duration_range': (2, 8)}},
        {'type': 'spike', 'tags': ['TI-101', 'PI-101', 'FI-201', 'PI-501', 'PI-502', 'VI-301', 'AI-901'], 'params': {'multiplier_range': (3, 8), 'duration_points_range': (1, 3)}},
        {'type': 'noise_burst', 'tags': ['TI-201', 'FI-101', 'VI-301', 'LI-401', 'AI-901', 'PI-401'], 'params': {'noise_multiplier_range': (3, 8), 'duration_range_hours': (1, 4)}},
        {'type': 'silent_lie', 'tags': ['TI-101', 'TI-201', 'PI-101', 'LI-101', 'FI-201'], 'params': {'offset_fraction_range': (0.02, 0.06), 'duration_range': (2, 6)}},
        {'type': 'sensor_drift', 'tags': ['PI-502', 'FI-601', 'FI-301', 'PI-501'], 'params': {'drift_rate_range': (0.005, 0.02)}},
    ]

    def __init__(self, seed: int = None, start_time: datetime = None):
        self.rng = random.Random(seed)
        if seed is not None:
            random.seed(seed)
        self.start_time = start_time or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self._prev_values: Dict[str, float] = {}
        self._deviations: Dict[str, float] = {}
        self.ar_coeff = 0.85
        self.active_anomalies: Dict[str, Dict] = {}
        self._generate_random_anomalies()

    def _generate_random_anomalies(self):
        num_anomalies = self.rng.randint(2, 4)
        used_tags = set()
        chosen = []

        candidates = list(self.ANOMALY_TEMPLATES)
        self.rng.shuffle(candidates)

        for template in candidates:
            if len(chosen) >= num_anomalies:
                break
            available_tags = [t for t in template['tags'] if t not in used_tags]
            if not available_tags:
                continue
            tag = self.rng.choice(available_tags)
            used_tags.add(tag)
            config = self.TAG_CONFIGS[tag]
            anomaly = {'type': template['type'], 'tag': tag}

            start_hour = self.rng.randint(1, 16)
            start_minute = self.rng.randint(0, 59)

            if template['type'] == 'sensor_drift':
                drift_range = template['params']['drift_rate_range']
                anomaly['start_hour'] = start_hour
                anomaly['start_minute'] = start_minute
                anomaly['duration_hours'] = self.rng.randint(4, min(10, 24 - start_hour - 1))
                anomaly['drift_rate'] = self.rng.uniform(*drift_range)
                if config['data_type'] in ('Pressure', 'Flow', 'Level', 'Conductivity'):
                    anomaly['drift_rate'] *= config['base'] * 0.01

            elif template['type'] == 'stuck_value':
                anomaly['start_hour'] = start_hour
                anomaly['start_minute'] = start_minute
                anomaly['duration_hours'] = self.rng.randint(*template['params']['duration_range'])
                anomaly['stuck_value'] = round(config['base'] + self.rng.uniform(-config['noise'], config['noise']), 3)

            elif template['type'] == 'spike':
                anomaly['start_hour'] = start_hour
                anomaly['start_minute'] = start_minute
                anomaly['duration_hours'] = 1
                anomaly['spike_multiplier'] = self.rng.uniform(*template['params']['multiplier_range'])
                anomaly['spike_points'] = self.rng.randint(*template['params']['duration_points_range'])

            elif template['type'] == 'noise_burst':
                anomaly['start_hour'] = start_hour
                anomaly['start_minute'] = start_minute
                anomaly['duration_hours'] = self.rng.uniform(*template['params']['duration_range_hours'])
                anomaly['noise_multiplier'] = self.rng.uniform(*template['params']['noise_multiplier_range'])

            elif template['type'] == 'silent_lie':
                anomaly['start_hour'] = start_hour
                anomaly['start_minute'] = start_minute
                anomaly['duration_hours'] = self.rng.randint(*template['params']['duration_range'])
                offset_fraction = self.rng.uniform(*template['params']['offset_fraction_range'])
                anomaly['offset'] = round(-config['base'] * offset_fraction, 3)
                if config['data_type'] == 'Temperature':
                    anomaly['offset'] = round(-self.rng.uniform(2, 5), 3)

            chosen.append(anomaly)
            self.active_anomalies[tag] = anomaly

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
            max_dev = abs(config['base'] - config.get('normal_min', config['base'] - config['base'] * 0.3))
            max_allowed = max(max_dev, config['noise'] * 10)
            deviations[tag_id] = max(-max_allowed, min(max_allowed, dev))

        return deviations

    def _apply_anomaly(self, tag_id: str, timestamp: datetime, value: float, config: Dict) -> tuple:
        anomaly = self.active_anomalies.get(tag_id)
        if not anomaly:
            return value, None

        anomaly_start = self.start_time.replace(hour=anomaly['start_hour'], minute=anomaly['start_minute'])
        anomaly_end = anomaly_start + timedelta(hours=anomaly.get('duration_hours', 1))

        if not (anomaly_start <= timestamp <= anomaly_end):
            return value, None

        if anomaly['type'] == 'sensor_drift':
            hours_elapsed = (timestamp - anomaly_start).total_seconds() / 3600
            drift = hours_elapsed * anomaly['drift_rate']
            return value + drift, 'sensor_drift'

        elif anomaly['type'] == 'stuck_value':
            return anomaly['stuck_value'], 'stuck_value'

        elif anomaly['type'] == 'spike':
            spike_points = anomaly.get('spike_points', 1)
            seconds_into_anomaly = (timestamp - anomaly_start).total_seconds()
            interval = 30
            local_index = int(seconds_into_anomaly / interval) % max(spike_points * 10, 1)
            if local_index < spike_points:
                return value + config['noise'] * anomaly['spike_multiplier'], 'spike'
            return value, None

        elif anomaly['type'] == 'noise_burst':
            burst_noise = random.gauss(0, config['noise'] * anomaly['noise_multiplier'])
            return value + burst_noise, 'noise_burst'

        elif anomaly['type'] == 'silent_lie':
            return value + anomaly['offset'], 'silent_lie'

        return value, None

    def generate_value(self, tag_id: str, timestamp: datetime) -> Dict[str, Any]:
        if tag_id not in self.TAG_CONFIGS:
            raise ValueError(f"Unknown tag: {tag_id}")
        config = self.TAG_CONFIGS[tag_id]

        noise = self._get_noise(config['noise'])
        causal_dev = self._deviations.get(tag_id, 0.0)
        hour_variation = math.sin(2 * math.pi * timestamp.hour / 24) * config['noise'] * 0.3

        prev = self._prev_values.get(tag_id, config['base'])
        natural_value = config['base'] + causal_dev + hour_variation + noise
        true_value = self.ar_coeff * prev + (1 - self.ar_coeff) * natural_value

        pre_anomaly_value = true_value
        true_value, anomaly_type = self._apply_anomaly(tag_id, timestamp, true_value, config)

        self._prev_values[tag_id] = pre_anomaly_value
        reported_value = round(true_value, 3)

        is_anomaly = anomaly_type is not None

        quality_code = 'Good'
        if random.random() < 0.02:
            quality_code = 'Warning'
        if random.random() < 0.005:
            quality_code = 'Bad'

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
                'scan_rate_sec': 30,
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
        for tag_id, anomaly in self.active_anomalies.items():
            if anomaly['type'] == 'silent_lie':
                return {'tag_id': tag_id, **anomaly}
        return {}

    def get_active_anomalies(self) -> List[Dict]:
        return [{'tag_id': tag, **anomaly} for tag, anomaly in self.active_anomalies.items()]


if __name__ == '__main__':
    for seed in [42, 123, 999]:
        print(f"\n=== Seed {seed} ===")
        simulator = TagSimulator(seed=seed)
        for a in simulator.get_active_anomalies():
            print(f"  {a['tag_id']}: {a['type']} at hour {a['start_hour']}:{a['start_minute']:02d}, duration {a.get('duration_hours', 'N/A')}h")