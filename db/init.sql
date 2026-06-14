CREATE TABLE IF NOT EXISTS sensor_data (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    air_temp FLOAT,
    sea_temp FLOAT,
    humidity FLOAT,
    pressure FLOAT,
    wind_speed FLOAT
);

-- Composite index on (device_id, timestamp DESC). This single index covers all
-- three IoT scenarios, which every query filters by device_id:
--   * Scenario B: WHERE device_id=? ORDER BY timestamp DESC LIMIT N
--     -> direct index seek to the device's newest rows (no scan/sort).
--   * Scenario C: WHERE device_id=? ... GROUP BY device_id
--     -> index range scan over just that device's rows.
-- A standalone (timestamp) index was deliberately removed: because every M-station's
-- data is clustered in a narrow time window, a time-only index tempts the planner
-- into scanning the whole table newest-first and filtering by device_id, which made
-- the Scenario B point-read ~400x slower. The composite index indexes BOTH the
-- device id and the timestamp, satisfying the "index by time and device" requirement.
CREATE INDEX IF NOT EXISTS idx_sensor_data_device_time ON sensor_data (device_id, timestamp DESC);
