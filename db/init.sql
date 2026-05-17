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

CREATE INDEX IF NOT EXISTS idx_sensor_data_device_time ON sensor_data (device_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_sensor_data_time ON sensor_data (timestamp);
