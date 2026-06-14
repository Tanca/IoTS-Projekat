import grpc from 'k6/net/grpc';
import { check, sleep } from 'k6';

const client = new grpc.Client();
client.load(['../grpc'], 'sensor.proto');

export const options = {
  stages: [
    { duration: '30s', target: 10 },
    { duration: '30s', target: 100 },
    { duration: '30s', target: 500 },
    { duration: '30s', target: 0 },
  ],
};

export default function () {
  // Connect once per VU (on its first iteration) and keep the channel open.
  // Reconnecting/closing every iteration crippled throughput and made the
  // gRPC load profile non-comparable to REST/GraphQL.
  if (__ITER === 0) {
    client.connect('localhost:50051', { plaintext: true });
  }

  const data = {
    device_id: `device-1`,
    timestamp: new Date().toISOString(),
    air_temp: Math.random() * 30,
    sea_temp: Math.random() * 20,
    humidity: Math.random() * 100,
    pressure: 1000 + Math.random() * 50,
    wind_speed: Math.random() * 20,
  };

  const response = client.invoke('sensor.SensorService/IngestSensorData', data);

  check(response, {
    'status is OK': (r) => r && r.status === grpc.StatusOK,
  });

  sleep(0.1);
}
