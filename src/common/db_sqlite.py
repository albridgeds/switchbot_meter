import sqlite3
import os
import pandas as pd


DB_DIR = os.path.join(os.path.dirname(__file__), "../../data")
os.makedirs(DB_DIR, exist_ok=True)


class SqlLite:

    def __init__(self, mac_address):
        safe_mac = mac_address.replace(":", "")
        self.db_path = os.path.join(DB_DIR, f"{safe_mac}.db")
        self.conn = sqlite3.connect(self.db_path)

    def write_to_sqlite(self, df: pd.DataFrame):
        df.to_sql("readings", self.conn, if_exists="append", index=False, method="multi", chunksize=10000)

    def upsert(self, df: pd.DataFrame):
        min_ts = df["timestamp"].min()
        max_ts = df["timestamp"].max()
        cursor = self.conn.cursor()
        cursor.execute(f'DELETE FROM readings WHERE timestamp BETWEEN "{min_ts}" AND "{max_ts}"')
        self.write_to_sqlite(df)

    def get_last_reading(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT MAX(timestamp) FROM readings')
        return cursor.fetchone()[0]

    def check(self):
        cursor = self.conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM readings')
        total_count = cursor.fetchone()
        print("Total number of readings:", total_count)

        cursor.execute('SELECT MIN(timestamp), MAX(timestamp) FROM readings')
        timestamps = cursor.fetchone()
        print("Min/max timestamps:", timestamps)
