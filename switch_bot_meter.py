import struct
import time
import asyncio
from bleak import BleakClient
from tqdm import tqdm


# The API endpoint
url = "https://api.switch-bot.com"
service_code = "CBA20D00-224D-11E6-9FB8-0002A5D5C51B"
write_code = "CBA20002-224D-11E6-9FB8-0002A5D5C51B"
read_code = "CBA20003-224D-11E6-9FB8-0002A5D5C51B"


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
CONNECT_ATTEMPT = 5
STARTNOTIFY_TIMEOUT = 10.0
GETDATA_TIMEOUT = 5.0

COMMAND_STATUS = [0x57, 0x02]
COMMAND_CURRENT_READINGS = [0x57, 0x0f, 0x31]
COMMAND_3A = [0x57, 0x0f, 0x3a]
COMMAND_3B = [0x57, 0x0f, 0x3b, 0x00]
COMMAND_3C = [0x57, 0x0f, 0x3c, 0x00]

# commands = {
#     "3C": {
#         "base": [0x57, 0x0f, 0x3c, 0x00],
#         "parser": self._parse_3c()
#     },
# }


class SwitchBotMeter:

    def __init__(self, address):
        self.address = address
        self.cur_status = 0
        self.cur_command = 0
        self.cur_timestamp = 0
        self.memory_start = 0
        self.memory_end = 0
        self.max_delta = 0
        self.readings = {}
        self.client = BleakClient(address)

    def get_current_readings(self):
        # status + temperature + battery
        pass

    def read_from_memory(self, dt_start=None, dt_end=None):
        asyncio.run(self._read_from_memory(dt_start, dt_end))
        return self.readings

    @staticmethod
    def _parce_31(packed):
        # Get temperature and related characteristics
        res = packed[0]
        temperature = (packed[2] & 0b01111111) + (
            (packed[1] & 0b00001111) / 10
        )  # Absolute value of temp
        if not (packed[2] & 0b10000000):  # Is temp negative?
            temperature = -temperature
        if not (packed[3] & 0b10000000):  # C or F?
            temp_scale = "C"
        else:
            temp_scale = "F"
            temperature = round(
                temperature * 1.8 + 32, 1
            )  # Convert to F
        # temperature2 = round(temperature * 1.8 + 32, 1)
        # Get other info
        humidity = packed[3] & 0b01111111
        print(res, temperature, temp_scale, humidity)

    def _parse_3b(self, resp):
        self.memory_start, self.memory_end, self.max_delta, _ = struct.unpack(">IIHH", resp)
        # print(timestamp_start, timestamp_end, max_delta)
        # return timestamp_start, timestamp_end, max_delta

    def _parse_3c(self, resp):
        # readings = []
        for iter_num, ind in enumerate(range(0, len(resp), 5)):
            # print(ind, iter_num)
            unix_time = self.memory_start + (self.cur_timestamp + iter_num * 2) * 120
            temperature = (resp[ind+3] & 0b01111111) + (resp[ind+2] & 0b00001111) / 10
            humidity = resp[ind+4] & 0b01111111
            temp_negative = (resp[ind+3] & 0b10000000)
            temp_scale_F = (resp[ind+4] & 0b10000000)
            # readings.append({'t': temperature, 'h': humidity})
            self.readings[unix_time] = {'temp': temperature, 'humidity': humidity}
            # print(i, temperature, humidity, temp_negative, temp_scale_F)
        # return readings

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
        # print("\nresponse:", "{0}".format(data.hex()))
        # print("response:", " ".join([hex(x) for x in data]))

        status_byte = data[0]
        self.cur_status = status_byte
        if status_byte != 1:
            print('status', status_byte, status_code[status_byte])
            return

        if self.cur_command == "3c":
            self._parse_3c(data[1:])
            # payload = self._parse_3c(data[1:])
            # for i in range(len(payload)):
            #     unix_time = self.memory_start + (self.cur_timestamp + i * 2) * 120
            #     self.readings[unix_time] = payload[i]

        elif self.cur_command == "3b":
            # self.memory_start, self.memory_end, self.max_delta = self._parse_3b(data[1:])
            self._parse_3b(data[1:])
        else:
            print("unknown message type", self.cur_command)
            return None
        # loop.call_soon_threadsafe(dataReceived.set_result, payload)

    async def _send_command_and_wait_for_response(self, command, command_id):
        # print("command:", "".join('{:02x} '.format(x) for x in command))
        self.cur_command = command_id
        self.cur_status = 0
        await self.client.write_gatt_char(write_code, bytearray(command), response=True)
        while True:
            await asyncio.sleep(COMMAND_SLEEP)
            if self.cur_status != 0:
                break
            # print('waiting...')

    async def _read_from_memory(self, dt_start=None, dt_end=None):

        try:
            # loop = asyncio.get_event_loop()
            # dataReceived = loop.create_future()

            # set connection
            await self._connect_meter()
            # get and parse the response
            await asyncio.wait_for(self.client.start_notify(read_code, self._collect),
                                   timeout=STARTNOTIFY_TIMEOUT)

            # get the timestamps of the first and the last available readings
            await self._send_command_and_wait_for_response(COMMAND_3B, '3b')
            # print('3b response:', self.memory_start, self.memory_end, self.max_delta)
            memory_start = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(self.memory_start))
            memory_end = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(self.memory_end))
            print(f"available interval: {memory_start} - {memory_end}")

            if dt_start is not None or dt_end is not None:
                print(f"input interval:     {dt_start} - {dt_end}")
                dt_start = int(time.mktime(time.strptime(dt_start, "%Y-%m-%d %H:%M:%S")))
                dt_end = int(time.mktime(time.strptime(dt_end, "%Y-%m-%d %H:%M:%S")))

            # fix the input
            dt_start_fixed_unix = max(dt_start, self.memory_start) if dt_start is not None else self.memory_start
            dt_end_fixed_unix = min(dt_end, self.memory_end) if dt_end is not None else self.memory_end
            dt_start_fixed = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(dt_start_fixed_unix))
            dt_end_fixed = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(dt_end_fixed_unix))
            print(f"requested interval: {dt_start_fixed} - {dt_end_fixed}")

            # calculate deltas
            delta_start = int(((dt_start_fixed_unix - self.memory_start) / 120) // 6) * 6
            # delta_start = int(delta_start // 6) * 6
            # delta_end = (dt_end - self.memory_start) / 120
            # delta_end = int(delta_end // 6) * 6
            delta_end = int(((dt_end_fixed_unix - self.memory_start) / 120) // 6) * 6
            print('deltas:', delta_start, delta_end)
            print()

            for delta in tqdm(range(delta_start, delta_end, 6)):
                if delta > self.max_delta:
                    break
                # num_byte = [0x04] if self.max_delta - delta < 2 else [0x06]
                num_byte = [0x06]

                self.cur_timestamp = delta
                dt_bytes = [x for x in struct.pack(">H", delta)]
                command = COMMAND_3C + dt_bytes + num_byte
                await self._send_command_and_wait_for_response(command, '3c')

            # logger.debug("got data, closing")
            print("got data, closing")
            await self.client.stop_notify(read_code)
        except asyncio.TimeoutError as e:
            # logger.error("timed out", e)
            print('time out', e)
        except Exception as e:
            # logger.error(e)
            print('error', e)
        finally:
            await self.client.disconnect()
