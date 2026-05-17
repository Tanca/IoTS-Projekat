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
  const res = http.get('http://localhost:3000/api/sensor-data/aggregate?device_id=M1');
  
  check(res, {
    'is status 200': (r) => r.status === 200,
    'has avg_air_temp': (r) => JSON.parse(r.body)[0].hasOwnProperty('avg_air_temp'),
  });
  sleep(0.1);
}
