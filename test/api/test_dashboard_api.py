import sqlite3
import time
from fastapi.testclient import TestClient
from datetime import datetime

import pytest

from src.api.dashboard_api import app


@pytest.fixture()
def client():
    return TestClient(app)


def create_db(path, rows):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS readings (timestamp INTEGER, temp REAL, humidity INTEGER)")
    cur.executemany("INSERT INTO readings (timestamp, temp, humidity) VALUES (?, ?, ?)", rows)
    conn.commit()
    conn.close()


def test_readings_default_days(monkeypatch, tmp_path, client):
    # create temp data dir and db
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "sensor1.db"
    now = int(time.time())
    rows = [
        (now, 21.5, 40),
        (now - 2 * 86400, 19.0, 50),
    ]
    create_db(str(db_path), rows)

    # monkeypatch project root resolution so module looks into tmp_path as project root
    import src.api.dashboard_api as mod
    class DummyResolve:
        def __init__(self, path):
            self._path = path
        def resolve(self):
            class R:
                pass
            r = R()
            # parents[2] should be tmp_path
            r.parents = [None, None, tmp_path]
            return r
    monkeypatch.setattr(mod, 'Path', DummyResolve)

    resp = client.get('/api/readings')
    assert resp.status_code == 200
    data = resp.json()
    # data is dict mapping sensor->points
    assert isinstance(data, dict)
    all_points = []
    for v in data.values():
        all_points.extend(v)
    assert any(p['temp'] == 21.5 for p in all_points)
    assert any(p['temp'] == 19.0 for p in all_points)


def test_readings_days_filter(monkeypatch, tmp_path, client):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "sensorA.db"
    now = int(time.time())
    rows = [
        (now, 22.0, 41),
        (now - 5 * 86400, 18.0, 55),
    ]
    create_db(str(db_path), rows)

    import src.api.dashboard_api as mod
    class DummyResolve:
        def __init__(self, path):
            self._path = path
        def resolve(self):
            class R:
                pass
            r = R()
            r.parents = [None, None, tmp_path]
            return r
    monkeypatch.setattr(mod, 'Path', DummyResolve)

    # days=1 -> only recent row across sensors
    resp = client.get('/api/readings?days=1')
    assert resp.status_code == 200
    data = resp.json()
    all_points = []
    for v in data.values():
        all_points.extend(v)
    assert len(all_points) == 1
    assert all_points[0]['temp'] == 22.0

    # days=10 -> both rows
    resp = client.get('/api/readings?days=10')
    data = resp.json()
    all_points = []
    for v in data.values():
        all_points.extend(v)
    assert len(all_points) == 2
