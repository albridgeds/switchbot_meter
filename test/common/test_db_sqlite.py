import sqlite3
import pandas as pd
import pytest
from datetime import datetime

from src.common.db_sqlite import SqlLite


def test_sqlite_upsert_idempotent(tmp_path, monkeypatch):
    # Redirect DB_DIR by monkeypatching module constant
    import src.common.db_sqlite as dbmod
    monkeypatch.setattr(dbmod, 'DB_DIR', str(tmp_path))

    mac = "AA:BB:CC:DD:EE:FF"
    s = SqlLite(mac)

    # ensure the readings table exists (upsert expects it)
    cur = s.conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS readings (timestamp TEXT, temp REAL, humidity INTEGER)")
    s.conn.commit()

    df = pd.DataFrame({
        'timestamp': [datetime.fromtimestamp(1600000000), datetime.fromtimestamp(1600000060)],
        'temp': [20.0, 20.1],
        'humidity': [50, 51]
    })
    s.upsert(df)

    cur.execute('SELECT COUNT(*) FROM readings')
    count = cur.fetchone()[0]
    assert count == 2

    # Upsert the same data again
    s.upsert(df)
    cur.execute('SELECT COUNT(*) FROM readings')
    count = cur.fetchone()[0]
    assert count == 2
