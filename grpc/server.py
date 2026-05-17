import os
import sys
import grpc
from concurrent import futures
import psycopg2
import psycopg2.extras
from psycopg2 import pool

import sensor_pb2
import sensor_pb2_grpc

db_url = os.getenv("DATABASE_URL", "postgresql://iot_user:iot_password@localhost:5432/iot_db")

class SensorServiceServicer(sensor_pb2_grpc.SensorServiceServicer):
    def __init__(self):
        self.db_pool = pool.ThreadedConnectionPool(1, 20, db_url)

    def IngestSensorData(self, request, context):
        conn = self.db_pool.getconn()
        try:
            cursor = conn.cursor()
            query = """
                INSERT INTO sensor_data (device_id, timestamp, air_temp, sea_temp, humidity, pressure, wind_speed)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
            """
            cursor.execute(query, (
                request.device_id, request.timestamp, 
                request.air_temp, request.sea_temp, request.humidity, 
                request.pressure, request.wind_speed
            ))
            new_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            return sensor_pb2.IngestResponse(message="Success", id=str(new_id))
        except Exception as e:
            conn.rollback()
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return sensor_pb2.IngestResponse()
        finally:
            self.db_pool.putconn(conn)

    def GetSelectiveData(self, request, context):
        conn = self.db_pool.getconn()
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            limit = request.limit if request.limit > 0 else 10
            query = """
                SELECT timestamp, air_temp, humidity 
                FROM sensor_data 
                WHERE device_id = %s 
                ORDER BY timestamp DESC 
                LIMIT %s
            """
            cursor.execute(query, (request.device_id, limit))
            rows = cursor.fetchall()
            cursor.close()

            response = sensor_pb2.SelectiveResponse()
            for row in rows:
                item = response.data.add()
                item.timestamp = str(row['timestamp'])
                item.air_temp = row['air_temp'] if row['air_temp'] is not None else 0.0
                item.humidity = row['humidity'] if row['humidity'] is not None else 0.0
            return response
        except Exception as e:
            conn.rollback()
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return sensor_pb2.SelectiveResponse()
        finally:
            self.db_pool.putconn(conn)

    def GetAggregatedData(self, request, context):
        conn = self.db_pool.getconn()
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            query = """
                SELECT 
                  device_id,
                  AVG(air_temp)::float as avg_air_temp,
                  MAX(air_temp) as max_air_temp,
                  MIN(air_temp) as min_air_temp,
                  AVG(humidity)::float as avg_humidity,
                  COUNT(*)::int as total_readings
                FROM sensor_data
                WHERE 1=1
            """
            params = []
            if request.device_id:
                query += " AND device_id = %s"
                params.append(request.device_id)
            if request.start_time:
                query += " AND timestamp >= %s"
                params.append(request.start_time)
            if request.end_time:
                query += " AND timestamp <= %s"
                params.append(request.end_time)

            query += " GROUP BY device_id"

            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            cursor.close()

            response = sensor_pb2.AggregateResponse()
            for row in rows:
                item = response.data.add()
                item.device_id = row['device_id']
                item.avg_air_temp = row['avg_air_temp'] if row['avg_air_temp'] is not None else 0.0
                item.max_air_temp = row['max_air_temp'] if row['max_air_temp'] is not None else 0.0
                item.min_air_temp = row['min_air_temp'] if row['min_air_temp'] is not None else 0.0
                item.avg_humidity = row['avg_humidity'] if row['avg_humidity'] is not None else 0.0
                item.total_readings = row['total_readings']
            return response
        except Exception as e:
            conn.rollback()
            context.set_details(str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            return sensor_pb2.AggregateResponse()
        finally:
            self.db_pool.putconn(conn)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    sensor_pb2_grpc.add_SensorServiceServicer_to_server(SensorServiceServicer(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("🚀 gRPC Server running on port 50051")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
