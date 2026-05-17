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

const query = `
  query GetAggregatedData($device_id: String) {
    getAggregatedData(device_id: $device_id) {
      device_id
      avg_air_temp
      max_air_temp
      min_air_temp
      avg_humidity
      total_readings
    }
  }
`;

export default function () {
  const payload = JSON.stringify({
    query: query,
    variables: {
      device_id: 'M1'
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
