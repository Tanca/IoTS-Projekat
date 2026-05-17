import os
import csv
import psycopg2
import sys

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("DATABASE_URL is not set.")
    sys.exit(1)

conn = psycopg2.connect(db_url)
cursor = conn.cursor()

csv_file = "/app/dataset.csv"



def to_float(val):
    if not val or val.lower() == 'nan':
        return None
    try:
        return float(val)
    except:
        return None

print("Starting to ingest dataset.csv into PostgreSQL...")

batch_size = 5000
batch = []
count = 0

with open(csv_file, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    next(reader, None)
    next(reader, None)

    for row in reader:
        if len(row) < 17:
            continue
        
        device_id = row[0]
        timestamp_str = row[3]
        if not device_id or not timestamp_str:
            continue

        pressure = to_float(row[4])
        wind_speed = to_float(row[6])
        air_temp = to_float(row[12])
        sea_temp = to_float(row[14])
        humidity = to_float(row[15])

        batch.append((device_id, timestamp_str, air_temp, sea_temp, humidity, pressure, wind_speed))
        
        if len(batch) >= batch_size:
            args_str = ','.join(cursor.mogrify("(%s,%s,%s,%s,%s,%s,%s)", x).decode("utf-8") for x in batch)
            cursor.execute("INSERT INTO sensor_data (device_id, timestamp, air_temp, sea_temp, humidity, pressure, wind_speed) VALUES " + args_str)
            batch = []
            count += batch_size
            print(f"Ingested {count} rows...")

    if batch:
        args_str = ','.join(cursor.mogrify("(%s,%s,%s,%s,%s,%s,%s)", x).decode("utf-8") for x in batch)
        cursor.execute("INSERT INTO sensor_data (device_id, timestamp, air_temp, sea_temp, humidity, pressure, wind_speed) VALUES " + args_str)
        count += len(batch)
        print(f"Ingested {count} rows...")

conn.commit()
cursor.close()
conn.close()

print(f"Successfully finished ingesting {count} rows!")
