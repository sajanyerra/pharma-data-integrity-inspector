-- Seed 20 Pharma Process Tags

INSERT INTO tags (tag_id, tag_name, unit_type, data_type, normal_min, normal_max, scan_rate_sec, description) VALUES
-- Reactor R-101
('TI-101', 'Reactor Temp', 'Reactor R-101', 'Temperature', 150, 200, 5, 'Exothermic reaction temperature'),
('PI-101', 'Reactor Pressure', 'Reactor R-101', 'Pressure', 2, 5, 5, 'Reactor headspace pressure'),
('FI-101', 'Feed Flow', 'Reactor R-101', 'Flow', 100, 500, 5, 'Raw material feed rate'),
('LI-101', 'Reactor Level', 'Reactor R-101', 'Level', 30, 80, 5, 'Liquid level in reactor'),

-- Heat Exchanger HX-201
('TI-201', 'Heat Exchanger Outlet', 'HX-201', 'Temperature', 40, 80, 5, 'Product cooling temperature'),
('FI-201', 'Cooling Water Flow', 'HX-201', 'Flow', 200, 800, 5, 'Cooling water flow rate'),
('TI-202', 'HX Hot Side Outlet', 'HX-201', 'Temperature', 60, 100, 5, 'Process side outlet temp'),

-- Pump P-301
('PI-301', 'Pump Discharge Pressure', 'Pump P-301', 'Pressure', 3, 8, 5, 'Centrifugal pump discharge'),
('FI-301', 'Pump Flow', 'Pump P-301', 'Flow', 100, 400, 5, 'Pump flow rate'),
('VI-301', 'Pump Vibration', 'Pump P-301', 'Vibration', 0, 10, 5, 'Bearing vibration monitoring'),

-- Tank T-401
('TI-401', 'Tank Temperature', 'Tank T-401', 'Temperature', 20, 40, 5, 'Storage tank temperature'),
('LI-401', 'Tank Level', 'Tank T-401', 'Level', 10, 90, 5, 'Tank liquid level'),
('PI-401', 'Tank Pressure', 'Tank T-401', 'Pressure', 0.5, 2, 5, 'Tank headspace pressure'),

-- Compressor C-501
('TI-501', 'Compressor Discharge', 'Comp C-501', 'Temperature', 80, 150, 5, 'Compressor outlet temp'),
('PI-501', 'Compressor Suction', 'Comp C-501', 'Pressure', 1, 3, 5, 'Compressor inlet pressure'),
('PI-502', 'Compressor Discharge', 'Comp C-501', 'Pressure', 6, 10, 5, 'Compressor outlet pressure'),

-- CIP System
('TI-601', 'CIP Supply Temp', 'CIP System', 'Temperature', 70, 85, 5, 'Clean-in-place supply temp'),
('FI-601', 'CIP Flow Rate', 'CIP System', 'Flow', 500, 1500, 5, 'CIP circulation flow'),
('CI-601', 'CIP Concentration', 'CIP System', 'Conductivity', 10, 50, 5, 'Caustic concentration'),

-- HVAC
('AI-901', 'Room Pressure', 'HVAC', 'Pressure', 10, 30, 5, 'Cleanroom differential pressure');
