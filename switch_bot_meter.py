import struct
import asyncio
from bleak import BleakClient
from tqdm import tqdm
from datetime import datetime
import pandas as pd
from bleak.exc import BleakError


# The API endpoint
# URL = "https://api.switch-bot.com"
SERVICE_CODE = "CBA20D00-224D-11E6-9FB8-0002A5D5C51B"
WRITE_CODE = "CBA20002-224D-11E6-9FB8-0002A5D5C51B"
READ_CODE = "CBA20003-224D-11E6-9FB8-0002A5D5C51B"


status_code = {
    0x01: "OK",
    0x02: "Error",
    0x03: "Busy device",
    0x04: "Communication protocol version incompatible",
    0x05: "Device does not support this Command",
    0x06: "Device low battery",
    0x07: "Device is encrypted",
    0x08: "Device is unencrypted",
    0x09: "Password error",
    0x0A: "Device does not support this encription method",
    0x0B: "Failed to locate a nearby mesh device",
    0x0C: "Failed to connect to the network",
}


DEVICE_SLEEP = 0.5
COMMAND_SLEEP = 0.01
RECONNECT_SLEEP = 1
CONNECT_ATTEMPT = 10
STARTNOTIFY_TIMEOUT = 10.0
GETDATA_TIMEOUT = 5.0

# STORAGE_ID = [0x03]

COMMAND_STATUS = [0x57, 0x02]
COMMAND_CURRENT_READINGS = [0x57, 0x0f, 0x31]
COMMAND_3A = [0x57, 0x0f, 0x3a]
COMMAND_3B = [0x57, 0x0f, 0x3b]
COMMAND_3C = [0x57, 0x0f, 0x3c]

COMMANDS = {
    "Status": [0x57, 0x02],
    "Current": [0x57, 0x0f, 0x31],
    "3A": [0x57, 0x0f, 0x3a],
    "3B": [0x57, 0x0f, 0x3b],
    "3C": [0x57, 0x0f, 0x3c],
}


def unix_timestamp_to_str(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


class SwitchBotMeter:

    def __init__(self, address):
        self.address = address
        self.cur_status = 0
        self.cur_command = 0
        self.cur_timestamp = 0
        self.memory_start_ts = 0
        self.memory_end_ts = 0
        self.max_delta = 0
        self.readings = {}
        self.client = BleakClient(address)

    async def read(self, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:

        end_ts = int(end_dt.timestamp())
        start_ts = int(start_dt.timestamp())

        try:
            await self._connect_meter()
            await asyncio.wait_for(
                self.client.start_notify(READ_CODE, self._collect),
                timeout=STARTNOTIFY_TIMEOUT
            )
            storage = await self._find_storage(start_ts, end_ts)
            if storage == -1:
                return
            await self._read_from_memory(storage)

            # logger.debug("got data, closing")
            print("got data, closing")
            await self.client.stop_notify(READ_CODE)
        except asyncio.TimeoutError as e:
            # logger.error("timed out", e)
            print('time out', e)
        except Exception as e:
            # logger.error(e)
            print('error', e)
        finally:
            if self.client:
                try:
                    if self.client.is_connected:
                        await self.client.disconnect()
                except (EOFError, BleakError) as e:
                    # Device/BlueZ already disconnected — safe to ignore
                    print(f"disconnect ignored: {e}")

        df_readings = pd.DataFrame(self.readings).T.reset_index().rename(columns={'index': 'timestamp'})
        df_readings['timestamp'] = pd.to_datetime(df_readings['timestamp'], unit='s')
        return df_readings

    @staticmethod
    def _parse_31(resp):
        temperature = (resp[1] & 0b01111111) + ((resp[0] & 0b00001111) / 10)  # Absolute value of temp
        if not (resp[1] & 0b10000000):  # Is temp negative?
            print("negative temperature")
            temperature = -temperature
        if not (resp[2] & 0b10000000):  # C or F?
            temp_scale = "C"
        else:
            temp_scale = "F"
            temperature = round(temperature * 1.8 + 32, 1)  # Convert to F
        # Get other info
        humidity = resp[2] & 0b01111111
        print("31 response:", temperature, temp_scale, humidity)

    def _parse_3b(self, resp):
        self.memory_start_ts, self.memory_end_ts, self.max_delta, _ = struct.unpack(">IIHH", resp)
        # print(self.memory_start, self.memory_end, self.max_delta, tmp)

    def _parse_3c(self, resp):
        for iter_num, ind in enumerate(range(0, len(resp), 5)):
            unix_time = self.memory_start_ts + (self.cur_timestamp + iter_num * 2) * 120
            temperature = (resp[ind+3] & 0b01111111) + (resp[ind+2] & 0b00001111) / 10
            humidity = resp[ind+4] & 0b01111111
            temp_negative = (resp[ind+3] & 0b10000000)
            temp_scale_F = (resp[ind+4] & 0b10000000)
            self.readings[unix_time] = {'temp': temperature, 'humidity': humidity}
            # print(iter_num, temperature, humidity, temp_negative, temp_scale_F)

    async def _connect_meter(self):
        for i in range(0, CONNECT_ATTEMPT):
            try:
                await self.client.connect()
                break
            except Exception as e:
                if i == CONNECT_ATTEMPT - 1:
                    # logger.error("BT connect failed, giving up")
                    print('BT connect failed, giving up')
                    raise e
                # logger.debug("BT connect failed, try {0}: {1}".format(i, e))
                print("BT connect failed, try {0}: {1}".format(i, e))
                await asyncio.sleep(RECONNECT_SLEEP)
        # logger.debug("connected!")
        print(self.address, 'connected!')

    def _collect(self, sender, data):
        # print('sender', sender)
        # print(self.cur_command, "response:", " ".join([hex(x) for x in data]))

        status_byte = data[0]
        self.cur_status = status_byte
        if status_byte != 1:
            print('status', status_byte, status_code[status_byte])
            return

        if self.cur_command == "31":
             self._parse_31(data[1:])
        elif self.cur_command == "3c":
            self._parse_3c(data[1:])
        elif self.cur_command == "3b":
            self._parse_3b(data[1:])
        else:
            print("unknown message type", self.cur_command)
            return None
        # loop.call_soon_threadsafe(dataReceived.set_result, payload)

    async def _send_command_and_wait_for_response(self, command, command_id):
        # print("sending command:", "".join('{:02x} '.format(x) for x in command))
        self.cur_command = command_id
        self.cur_status = 0
        await self.client.write_gatt_char(WRITE_CODE, bytearray(command), response=True)
        while True:
            await asyncio.sleep(COMMAND_SLEEP)
            if self.cur_status != 0:
                break

    async def _find_storage(self, start_ts: int = None, end_ts: int = None):

        for storage in range(5):
            command = COMMAND_3B + [storage]
            print(f'Checking storage #{storage}')
            await self._send_command_and_wait_for_response(command, '3b')

            print(f"Available interval: {unix_timestamp_to_str(self.memory_start_ts)} - {unix_timestamp_to_str(self.memory_end_ts)}")
            if self.memory_start_ts < start_ts < self.memory_end_ts:
                self.start_ts = max(start_ts, self.memory_start_ts) if start_ts else self.memory_start_ts
                self.end_ts = min(end_ts, self.memory_end_ts) if end_ts else self.memory_end_ts
                return storage

        print("storage not found")
        return -1

    async def _read_from_memory(self, storage):

        print(f"Request interval ({unix_timestamp_to_str(self.start_ts)} - {unix_timestamp_to_str(self.end_ts)}) from storage #{storage}")

        # calculate deltas between available and requested data
        delta_start = int(((self.start_ts - self.memory_start_ts) / 120) // 6) * 6
        delta_end = int(((self.end_ts - self.memory_start_ts) / 120) // 6) * 6
        print('deltas:', delta_start, delta_end)

        for delta in tqdm(range(delta_start, delta_end, 6)):
            if delta > self.max_delta:
                break
            # num_byte = [0x04] if self.max_delta - delta < 2 else [0x06]
            num_byte = [0x06]

            self.cur_timestamp = delta
            dt_bytes = [x for x in struct.pack(">H", delta)]
            command = COMMAND_3C + [storage] + dt_bytes + num_byte
            await self._send_command_and_wait_for_response(command, '3c')
