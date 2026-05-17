const { ApolloServer } = require('@apollo/server');
const { startStandaloneServer } = require('@apollo/server/standalone');
const { Pool } = require('pg');

const pool = new Pool({
  connectionString: process.env.DATABASE_URL || 'postgresql://iot_user:iot_password@localhost:5432/iot_db',
});

const typeDefs = `#graphql
  type SensorData {
    id: ID!
    device_id: String!
    timestamp: String!
    air_temp: Float
    sea_temp: Float
    humidity: Float
    pressure: Float
    wind_speed: Float
  }

  type AggregatedData {
    device_id: String!
    avg_air_temp: Float
    max_air_temp: Float
    min_air_temp: Float
    avg_humidity: Float
    total_readings: Int
  }

  type Query {
    getSensorData(device_id: String!, limit: Int): [SensorData]
    getAggregatedData(device_id: String, start_time: String, end_time: String): [AggregatedData]
  }

  type Mutation {
    ingestSensorData(
      device_id: String!
      timestamp: String!
      air_temp: Float
      sea_temp: Float
      humidity: Float
      pressure: Float
      wind_speed: Float
    ): SensorData
  }
`;

const resolvers = {
  Query: {
    getSensorData: async (_, { device_id, limit = 10 }) => {
      const query = 'SELECT * FROM sensor_data WHERE device_id = $1 ORDER BY timestamp DESC LIMIT $2';
      const result = await pool.query(query, [device_id, limit]);
      return result.rows;
    },
    getAggregatedData: async (_, { device_id, start_time, end_time }) => {
      let query = `
        SELECT 
          device_id,
          AVG(air_temp) as avg_air_temp,
          MAX(air_temp) as max_air_temp,
          MIN(air_temp) as min_air_temp,
          AVG(humidity) as avg_humidity,
          COUNT(*)::int as total_readings
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

      query += ' GROUP BY device_id';
      const result = await pool.query(query, values);
      return result.rows;
    },
  },
  Mutation: {
    ingestSensorData: async (_, args) => {
      const { device_id, timestamp, air_temp, sea_temp, humidity, pressure, wind_speed } = args;
      const query = `
        INSERT INTO sensor_data (device_id, timestamp, air_temp, sea_temp, humidity, pressure, wind_speed)
        VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *
      `;
      const values = [device_id, timestamp, air_temp, sea_temp, humidity, pressure, wind_speed];
      const result = await pool.query(query, values);
      return result.rows[0];
    },
  },
};

async function startServer() {
  const server = new ApolloServer({ typeDefs, resolvers });
  const { url } = await startStandaloneServer(server, {
    listen: { port: process.env.PORT || 4000 },
  });
  console.log(`🚀 GraphQL Server ready at ${url}`);
}

startServer();
