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

export default function () {
  const payload = JSON.stringify({
    device_id: `device-1`,
    timestamp: new Date().toISOString(),
    air_temp: Math.random() * 30,
    sea_temp: Math.random() * 20,
    humidity: Math.random() * 100,
    pressure: 1000 + Math.random() * 50,
    wind_speed: Math.random() * 20
  });

  const params = { headers: { 'Content-Type': 'application/json' } };
  const res = http.post('http://localhost:3000/api/sensor-data', payload, params);
  
  check(res, {
    'is status 201': (r) => r.status === 201,
  });
  sleep(0.1);
}
