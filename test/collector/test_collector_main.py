import pytest
from datetime import datetime
from src import config

from src.collector import main as collector_main


def test_convert_app_export_simple():
    import pandas as pd
    df = pd.DataFrame({
        'Date': ['Sep 01, 2025 12:00'],
        'Temperature_Celsius(℃)': [21.5],
        'Relative_Humidity(%)': [45]
    })
    out = collector_main.convert_app_export(df)
    assert 'timestamp' in out.columns
    assert out.iloc[0]['temp'] == 21.5


@pytest.mark.asyncio
async def test_main_with_test_data_and_sqlite_monkeypatch(monkeypatch, tmp_path):
    # Patch SqlLite to capture upsert calls and redirect DB_DIR
    calls = []

    class FakeSql:
        def __init__(self, mac):
            self.db_path = str(tmp_path / (mac.replace(':', '') + '.db'))

        def get_last_reading(self):
            # return ISO string
            return datetime.fromtimestamp(0).isoformat()

        def upsert(self, df):
            calls.append(('upsert', len(df)))

        def check(self):
            calls.append(('check', None))

    monkeypatch.setattr('src.collector.main.SqlLite', FakeSql)

    # Run main with use_test_data True
    await collector_main.main(dt=datetime.fromtimestamp(1600000000).isoformat(), duration=1, use_test_data=True, rewrite=True, room=None)

    # Assert that for each room in config.BL_MACS an upsert happened
    rooms = list(config.BL_MACS.keys())
    upsert_calls = [c for c in calls if c[0] == 'upsert']
    assert len(upsert_calls) == len(rooms)
