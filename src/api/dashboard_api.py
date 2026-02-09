from fastapi import FastAPI
from fastapi.responses import FileResponse
import sqlite3
from pathlib import Path
from datetime import datetime
import time
import logging
import math
from collections import defaultdict

try:
    # Preferred when running as a package module: uvicorn src.api.dashboard_api:app
    from .. import config  # type: ignore
except Exception:  # pragma: no cover
    # Fallbacks for ad-hoc runs where package context isn't set up
    try:
        from src import config  # type: ignore
    except Exception:
        import config  # type: ignore

app = FastAPI()

# build reverse map safe_mac (no colons, lower) -> room name
_reverse_mac_map = {mac.replace(':', '').lower(): name for name, mac in config.BL_MACS.items()}


@app.get("/")
def index():
    # serve the dashboard HTML
    index_file = Path(__file__).resolve().parent / "index.html"
    return FileResponse(index_file)


def to_unix(ts):
    """Convert various timestamp representations from SQLite to unix seconds (int).
    Handles int/float, byte strings, ISO strings, and common SQL datetime format 'YYYY-MM-DD HH:MM:SS'.
    """
    if ts is None:
        return None
    if isinstance(ts, int):
        return ts
    if isinstance(ts, float):
        return int(ts)
    if isinstance(ts, bytes):
        ts = ts.decode('utf-8')

    if isinstance(ts, str):
        s = ts.strip()
        if s.isdigit():
            return int(s)
        try:
            f = float(s)
            return int(f)
        except Exception:
            pass
        try:
            dt = datetime.fromisoformat(s)
            return int(dt.timestamp())
        except Exception:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s, fmt)
                return int(dt.timestamp())
            except Exception:
                continue
    try:
        return int(ts)
    except Exception:
        raise ValueError(f"Cannot parse timestamp value: {ts!r}")


@app.get("/api/readings")
def readings(days: int = 10, end: int | None = None):
    end_ts = int(time.time()) if end is None else int(end)
    cutoff = end_ts - int(days) * 86400

    project_root = Path(__file__).resolve().parents[2]
    data_dir = project_root / "data"

    sensors = {}

    if not data_dir.exists():
        return sensors

    for db_path in sorted(data_dir.glob("*.db")):
        sensor_stem = db_path.stem
        # map safe mac -> friendly room name when available
        sensor_name = _reverse_mac_map.get(sensor_stem.lower(), sensor_stem)
        # ensure sensor is present in response even if no recent points or on error
        sensors[sensor_name] = []

        try:
            conn = sqlite3.connect(str(db_path))
        except Exception as e:
            logging.warning("Cannot open DB %s: %s", db_path, e)
            continue

        try:
            rows = conn.execute("SELECT timestamp, temp, humidity FROM readings ORDER BY timestamp")
            fetched = rows.fetchall()
            points = []
            for ts, temp, hum in fetched:
                try:
                    t_unix = to_unix(ts)
                except ValueError:
                    continue
                if t_unix is None:
                    continue
                if t_unix < cutoff or t_unix > end_ts:
                    continue
                points.append({"t": int(t_unix), "temp": temp, "hum": hum})
            sensors[sensor_name] = points
            logging.info(
                "Sensor %s (from %s): %d points (window cutoff=%s end=%s)",
                sensor_name,
                sensor_stem,
                len(points),
                cutoff,
                end_ts,
            )
        except Exception as e:
            logging.warning("Error reading DB %s: %s", db_path, e)
        finally:
            conn.close()

    # Automatic aggregation: if total unique timestamps > threshold, aggregate into bins
    # desired_points selects approx how many points to keep on x-axis
    DESIRED_POINTS = 500
    # collect overall timestamps
    all_ts = set()
    for pts in sensors.values():
        for p in pts:
            all_ts.add(p['t'])
    if not all_ts:
        logging.info("No timestamps in window; sensors keys: %s", list(sensors.keys()))
        return sensors

    sorted_ts = sorted(all_ts)
    total_points = len(sorted_ts)
    logging.info("Total unique timestamps across sensors: %d", total_points)
    if total_points > DESIRED_POINTS:
        # Aggregate over the requested window to keep time scale consistent even with gaps.
        start = cutoff
        end_window = end_ts
        span = max(1, end_window - start)
        bin_seconds = math.ceil(span / DESIRED_POINTS)
        # choose rounding unit_seconds for labels (day/hour/minute/second)
        if bin_seconds >= 86400:
            unit_seconds = 86400
        elif bin_seconds >= 3600:
            unit_seconds = 3600
        elif bin_seconds >= 60:
            unit_seconds = 60
        else:
            unit_seconds = 1
        # aggregate per sensor
        for sensor_name, pts in sensors.items():
            logging.info("Aggregating sensor %s: %d points", sensor_name, len(pts))
            if not pts:
                continue
            bins = defaultdict(list)
            for p in pts:
                idx = (p['t'] - start) // bin_seconds
                bins[idx].append(p)
            # temporary store by rounded timestamp to merge collisions after rounding
            merged = defaultdict(list)
            for idx in sorted(bins.keys()):
                group = bins[idx]
                count = len(group)
                avg_t = int(sum(x['t'] for x in group) / count)
                avg_temp = sum(float(x['temp']) for x in group) / count
                avg_hum = sum(float(x['hum']) for x in group) / count
                # round avg_t to nearest unit_seconds
                rounded_t = int(round(avg_t / unit_seconds) * unit_seconds)
                if rounded_t < cutoff or rounded_t > end_ts:
                    continue
                merged[rounded_t].append({"t": rounded_t, "temp": avg_temp, "hum": avg_hum})
            # now compute final averages per rounded_t
            agg = []
            for rt in sorted(merged.keys()):
                group = merged[rt]
                count = len(group)
                avg_temp = sum(float(x['temp']) for x in group) / count
                avg_hum = sum(float(x['hum']) for x in group) / count
                agg.append({"t": rt, "temp": round(avg_temp, 3), "hum": int(round(avg_hum))})
            sensors[sensor_name] = agg
            logging.info("Sensor %s aggregated to %d points", sensor_name, len(agg))

    logging.info("Final sensors keys: %s", list(sensors.keys()))

    return sensors


@app.get("/api/sensors_info")
def sensors_info(days: int = 10, end: int | None = None):
    """Return counts of points per sensor before and after aggregation (for debugging)."""
    end_ts = int(time.time()) if end is None else int(end)
    cutoff = end_ts - int(days) * 86400

    project_root = Path(__file__).resolve().parents[2]
    data_dir = project_root / "data"

    pre_counts = {}
    post_counts = {}

    if not data_dir.exists():
        return {"pre": pre_counts, "post": post_counts}

    # first, compute pre_counts
    for db_path in sorted(data_dir.glob("*.db")):
        sensor_name = db_path.stem
        pre_counts[sensor_name] = 0
        try:
            conn = sqlite3.connect(str(db_path))
        except Exception:
            continue
        try:
            rows = conn.execute("SELECT timestamp, temp, humidity FROM readings ORDER BY timestamp")
            fetched = rows.fetchall()
            cnt = 0
            for ts, temp, hum in fetched:
                try:
                    t_unix = to_unix(ts)
                except Exception:
                    continue
                if t_unix is None:
                    continue
                if t_unix < cutoff or t_unix > end_ts:
                    continue
                cnt += 1
            pre_counts[sensor_name] = cnt
        finally:
            conn.close()

    # now call readings() to get post-aggregation sensors
    sensors = readings(days=days, end=end_ts)
    for name, pts in sensors.items():
        post_counts[name] = len(pts) if pts else 0

    return {"pre": pre_counts, "post": post_counts}
