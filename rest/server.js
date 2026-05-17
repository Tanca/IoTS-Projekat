const express = require('express');
const { Pool } = require('pg');
const swaggerUi = require('swagger-ui-express');
const swaggerDocument = require('./swagger.json');

const app = express();
app.use(express.json());

const pool = new Pool({
  connectionString: process.env.DATABASE_URL || 'postgresql://iot_user:iot_password@localhost:5432/iot_db',
});

app.use('/api-docs', swaggerUi.serve, swaggerUi.setup(swaggerDocument));

app.post('/api/sensor-data', async (req, res) => {
  const { device_id, timestamp, air_temp, sea_temp, humidity, pressure, wind_speed } = req.body;
  
  if (!device_id || !timestamp) {
    return res.status(400).json({ error: 'device_id and timestamp are required' });
  }

  try {
    const query = `
      INSERT INTO sensor_data (device_id, timestamp, air_temp, sea_temp, humidity, pressure, wind_speed)
      VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id
    `;
    const values = [device_id, timestamp, air_temp, sea_temp, humidity, pressure, wind_speed];
    const result = await pool.query(query, values);
    res.status(201).json({ id: result.rows[0].id, message: 'Data ingested successfully' });
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: 'Database error during ingestion' });
  }
});

app.get('/api/sensor-data/selective/:device_id', async (req, res) => {
  const { device_id } = req.params;
  const limit = req.query.limit || 10;
  
  try {
    const query = `
      SELECT * 
      FROM sensor_data 
      WHERE device_id = $1 
      ORDER BY timestamp DESC 
      LIMIT $2
    `;
    const result = await pool.query(query, [device_id, limit]);
    res.status(200).json(result.rows);
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: 'Database error' });
  }
});

app.get('/api/sensor-data/aggregate', async (req, res) => {
  const { device_id, start_time, end_time } = req.query;
  
  try {
    let query = `
      SELECT 
        device_id,
        AVG(air_temp) as avg_air_temp,
        MAX(air_temp) as max_air_temp,
        MIN(air_temp) as min_air_temp,
        AVG(humidity) as avg_humidity,
        COUNT(*) as total_readings
      FROM sensor_data
      WHERE 1=1
    `;
    const values = [];
    let paramIndex = 1;

    if (device_id) {
      query += ` AND device_id = $${paramIndex++}`;
      values.push(device_id);
    }
    if (start_time) {
      query += ` AND timestamp >= $${paramIndex++}`;
      values.push(start_time);
    }
    if (end_time) {
      query += ` AND timestamp <= $${paramIndex++}`;
      values.push(end_time);
    }

    query += ` GROUP BY device_id`;

    const result = await pool.query(query, values);
    res.status(200).json(result.rows);
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: 'Database error during aggregation' });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`REST API Service running on port ${PORT}`);
});
