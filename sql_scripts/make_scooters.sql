INSERT INTO scooters (model, battery_level, battery_consumption, speed_limit, location_id, status, last_maintenance_date)
VALUES
    -- Самокаты для локации "Север"
    ('Model A', 90, 1.5, 25.0, (SELECT location_id FROM locations WHERE name = 'Север'), 'available', '2024-12-10'),
    ('Model B', 80, 1.4, 23.0, (SELECT location_id FROM locations WHERE name = 'Север'), 'available', '2024-12-12'),
    ('Model C', 70, 1.6, 24.0, (SELECT location_id FROM locations WHERE name = 'Север'), 'on_maintenance', '2024-12-15'),
    
    -- Самокаты для локации "Юг"
    ('Model D', 85, 1.7, 22.0, (SELECT location_id FROM locations WHERE name = 'Юг'), 'available', '2024-12-11'),
    ('Model E', 75, 1.5, 20.0, (SELECT location_id FROM locations WHERE name = 'Юг'), 'available', '2024-12-14'),
    
    -- Самокаты для локации "Запад"
    ('Model F', 95, 1.3, 26.0, (SELECT location_id FROM locations WHERE name = 'Запад'), 'in_use', '2024-12-09'),
    ('Model G', 60, 1.4, 23.0, (SELECT location_id FROM locations WHERE name = 'Запад'), 'available', '2024-12-13'),
    
    -- Самокаты для локации "Восток"
    ('Model H', 88, 1.6, 24.5, (SELECT location_id FROM locations WHERE name = 'Восток'), 'available', '2024-12-12'),
    ('Model I', 77, 1.7, 21.0, (SELECT location_id FROM locations WHERE name = 'Восток'), 'on_maintenance', '2024-12-14'),
    ('Model J', 92, 1.5, 25.0, (SELECT location_id FROM locations WHERE name = 'Восток'), 'in_use', '2024-12-16');
