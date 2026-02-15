import struct
import asyncio
import pytest
from datetime import datetime
import pandas as pd

from src.collector.switch_bot_meter import SwitchBotMeter, unix_timestamp_to_str


def test_unix_timestamp_to_str():
    ts = 1700000000  # arbitrary
    s = unix_timestamp_to_str(ts)
    assert isinstance(s, str)


def test_parse_3b_sets_memory_fields():
    meter = SwitchBotMeter("AA:BB:CC:DD:EE:FF")
    start_ts = 1600000000
    end_ts = 1600003600
    max_delta = 42
    tmp = 0
    payload = struct.pack(">IIHH", start_ts, end_ts, max_delta, tmp)
    meter._parse_3b(payload)
    assert meter.memory_start_ts == start_ts
    assert meter.memory_end_ts == end_ts
    assert meter.max_delta == max_delta


def test_parse_3c_populates_readings():
    meter = SwitchBotMeter("AA:BB:CC:DD:EE:FF")
    # set memory start and current timestamp
    meter.memory_start_ts = 1000
    meter.cur_timestamp = 0

    # create two 5-byte blocks
    # each block: [b0, b1, temp_low_nibble, temp_high_byte, humidity]
    # temp uses resp[ind+3] and resp[ind+2]
    # set temp_high_byte = 0x12 (0b00010010 -> positive), temp_low_nibble = 0x03 -> temp = 0x12 + 0.3
    block1 = bytes([0x00, 0x00, 0x03, 0x12, 0x20])
    # second block, temp 0x13 + 0.5, humidity 0x25
    block2 = bytes([0x00, 0x00, 0x05, 0x13, 0x25])
    payload = block1 + block2

    meter._parse_3c(payload)

    # two entries expected, timestamps computed as memory_start_ts + (cur_timestamp + iter_num*2)*120
    ts1 = meter.memory_start_ts + (0 + 0 * 2) * 120
    ts2 = meter.memory_start_ts + (0 + 1 * 2) * 120
    assert ts1 in meter.readings
    assert ts2 in meter.readings
    assert "temp" in meter.readings[ts1]
    assert "humidity" in meter.readings[ts1]


def test_collect_handles_status_and_calls_parsers():
    meter = SwitchBotMeter("AA:BB:CC:DD:EE:FF")
    meter.readings = {}
    meter.memory_start_ts = 1000
    meter.cur_timestamp = 0
    # prepare a payload for _parse_3c with one block
    block = bytes([0x00, 0x00, 0x03, 0x12, 0x20])
    data = bytes([0x01]) + block  # status=1
    meter.cur_command = "3c"
    meter._collect(sender=1, data=data)
    # expect that readings were populated
    assert len(meter.readings) >= 1


@pytest.mark.asyncio
async def test_read_with_mocked_client(monkeypatch):
    # Monkeypatch BleakClient methods used by SwitchBotMeter.client
    class DummyClient:
        def __init__(self, addr):
            self.addr = addr
            self.is_connected = False

        async def connect(self):
            self.is_connected = True

        async def start_notify(self, code, callback):
            # simulate immediate start
            return

        async def stop_notify(self, code):
            return

        async def disconnect(self):
            self.is_connected = False

        async def write_gatt_char(self, code, data, response=True):
            # simulate an immediate response by calling the notification callback indirectly
            # nothing to do here for this test
            return

    monkeypatch.setattr("src.collector.switch_bot_meter.BleakClient", DummyClient)

    meter = SwitchBotMeter("AA:BB:CC:DD:EE:FF")

    # Patch internal methods: _find_storage to return storage index and _read_from_memory to set readings
    async def fake_find_storage(self, start_ts, end_ts):
        return 0

    async def fake_read_from_memory(self, storage):
        # populate some readings
        meter.readings[1600000000] = {"temp": 20.0, "humidity": 50}

    monkeypatch.setattr(SwitchBotMeter, "_find_storage", fake_find_storage)
    monkeypatch.setattr(SwitchBotMeter, "_read_from_memory", fake_read_from_memory)

    start_dt = datetime.fromtimestamp(1600000000)
    end_dt = datetime.fromtimestamp(1600003600)

    df = await meter.read(start_dt, end_dt)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert "temp" in df.columns
    assert "humidity" in df.columns
    assert pd.to_datetime(df.iloc[0]["timestamp"]) == pd.to_datetime(1600000000, unit='s')
