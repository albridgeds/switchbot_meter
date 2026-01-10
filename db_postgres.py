import psycopg2
import psycopg2.extras
import pandas as pd


HOST = 'localhost'
DBNAME = 'postgres'
USER = 'postgres'
PASSWORD = 'postgres'


class Postgres:

    def __init__(self):
        self.conn = psycopg2.connect(
            host=HOST, dbname=DBNAME, user=USER, password=PASSWORD
        )

    def write(self, df_readings, mac):
        df_readings['mac'] = mac
        data_to_write = df_readings[['timestamp', 'mac', 'temp', 'humidity']].values

        insert_sql = """
           INSERT INTO switchbot_meter (time, mac, temperature, humidity)
                VALUES %s
                ON CONFLICT (time, mac)
                --DO UPDATE SET (temperature, humidity) = (EXCLUDED.temperature, EXCLUDED.humidity);
                DO NOTHING;
        """
        with self.conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur, insert_sql, data_to_write, template=None, page_size=100
            )

    def read_all(self):
        query = "SELECT * FROM switchbot_meter"
        with self.conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
        readings = pd.DataFrame(rows, columns=['timestamp', 'mac', 'temp', 'humidity'])
        return readings
