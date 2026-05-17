import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 10 },
    { duration: '30s', target: 100 },
    { duration: '30s', target: 500 },
    { duration: '30s', target: 0 },
  ],
};

const mutation = `
  mutation IngestSensorData($device_id: String!, $timestamp: String!, $air_temp: Float, $sea_temp: Float, $humidity: Float, $pressure: Float, $wind_speed: Float) {
    ingestSensorData(device_id: $device_id, timestamp: $timestamp, air_temp: $air_temp, sea_temp: $sea_temp, humidity: $humidity, pressure: $pressure, wind_speed: $wind_speed) {
      id
    }
  }
`;

export default function () {
  const payload = JSON.stringify({
    query: mutation,
    variables: {
      device_id: `device-1`,
      timestamp: new Date().toISOString(),
      air_temp: Math.random() * 30,
      sea_temp: Math.random() * 20,
      humidity: Math.random() * 100,
      pressure: 1000 + Math.random() * 50,
      wind_speed: Math.random() * 20
    }
  });

  const params = { headers: { 'Content-Type': 'application/json' } };
  const res = http.post('http://localhost:4000/', payload, params);
  
  check(res, {
    'is status 200': (r) => r.status === 200,
    'no errors': (r) => !JSON.parse(r.body).errors,
  });
  sleep(0.1);
}
