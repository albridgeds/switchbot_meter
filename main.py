import argparse
import asyncio
import pandas as pd
from datetime import datetime, timedelta

import config
from switch_bot_meter import SwitchBotMeter
from db_sqlite import SqlLite
# from db_postgres import Postgres
from test.meter_data import METER_READINGS


def convert_app_export(df_export):

    df_readings = (
        df_export.rename(columns={
            'Date': 'timestamp',
            'Temperature_Celsius(℃)': 'temp',
            'Relative_Humidity(%)': 'humidity',
        })
        [['timestamp', 'temp', 'humidity']]
    )
    df_readings['timestamp'] = df_readings['timestamp'].str.replace('Sept', 'Sep')
    df_readings['timestamp'] = pd.to_datetime(df_readings['timestamp'], format="%b %d, %Y %H:%M")
    return df_readings


async def main(dt: str, duration: int, use_test_data: bool, rewrite: bool, room: str):

    end_dt = datetime.fromisoformat(dt) if dt else datetime.now()
    start_dt = end_dt - timedelta(minutes=duration)
    print(start_dt, end_dt)

    for room_name, bl_mac in config.BL_MACS.items():

        if room and room != room_name:
            continue

        sql_lite = SqlLite(bl_mac)

        if not rewrite:
            last_reading_dt = datetime.fromisoformat(sql_lite.get_last_reading())
            if last_reading_dt > end_dt:
                print("Last reading > end_dt, skip rewriting")
                return
            start_dt = max(start_dt, last_reading_dt)
            print("recalc start", start_dt)

        print(f"Reading {room_name} from {bl_mac}...")
        if use_test_data:
            readings = METER_READINGS
        else:
            meter = SwitchBotMeter(bl_mac)
            readings = await meter.read(start_dt, end_dt)

        print(f"Writing {len(readings)} readings to {sql_lite.db_path}...")
        sql_lite.upsert(readings)
        sql_lite.check()


    # save_readings(bl_mac_bedroom, "meter_bedroom.csv")

    # write app exported data to database
    # df_old = pd.read_csv("Bedroom_data.csv")
    # df_readings = convert_app_export(df_old)
    # write_to_postgres(df_readings, bl_mac_bedroom)

    # write app exported data to database
    # df_old = pd.read_csv("Children_data.csv")
    # df_readings = convert_app_export(df_old)
    # write_to_postgres(df_readings, bl_mac_childroom)

    # write collected readings to database
    # df_readings = pd.read_csv("meter_bedroom.csv", index_col=0)
    # df_readings['timestamp'] = pd.to_datetime(df_readings['timestamp'], unit='s')
    # write_to_postgres(df_readings, bl_mac_bedroom)

    # df_readings = pd.read_csv("meter_childroom.csv", index_col=0)
    # df_readings['timestamp'] = pd.to_datetime(df_readings['timestamp'], unit='s')
    # write_to_postgres(df_readings, bl_mac_childroom)


# def save_postgres_to_sqlite():
#     postgres = Postgres()
#     readings = postgres.read_all()
#     readings['temp'] = readings['temp'].astype(float)
#     for room, bl_mac in config.BL_MACS.items():
#         df = readings[readings["mac"] == bl_mac.lower()].drop("mac", axis='columns')
#         sql_lite = SqlLite(bl_mac)
#         print(f"Writing {len(df)} readings to {sql_lite.db_path}...")
#         sql_lite.upsert(df)
#         sql_lite.check()


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument("--dt", type=str, help="Reference date/datetime, ISO format: %Y-%m-%d (%H:%M:%S)")
    parser.add_argument("--duration", type=int, default=1440, help="Reading period, minutes")
    parser.add_argument("--use_test_data", action="store_true", default=False, help="Use test data instead of real sensors")
    parser.add_argument("--rewrite", action="store_true", default=False, help="Rewrite existing database records with the sensor data")
    parser.add_argument("--room", type=str, help="To request a single room only")
    args = parser.parse_args()

    asyncio.run(main(**vars(args)))
