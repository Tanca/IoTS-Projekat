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
  client.connect('localhost:50051', {
    plaintext: true
  });

  const data = {
    device_id: 'M1'
  };

  const response = client.invoke('sensor.SensorService/GetAggregatedData', data);

  check(response, {
    'status is OK': (r) => r && r.status === grpc.StatusOK,
  });

  client.close();
  sleep(0.1);
}
