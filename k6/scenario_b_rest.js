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
  const res = http.get('http://localhost:3000/api/sensor-data/selective/M1?limit=1');
  
  check(res, {
    'is status 200': (r) => r.status === 200,
  });
  sleep(0.1);
}
