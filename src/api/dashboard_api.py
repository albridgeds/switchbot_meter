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

# Constants
DESIRED_POINTS = 500
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

# Build reverse map safe_mac (no colons, lower) -> room name
_reverse_mac_map = {mac.replace(':', '').lower(): name for name, mac in config.BL_MACS.items()}


@app.get("/")
def index():
    """Serve the dashboard HTML."""
    return FileResponse(Path(__file__).resolve().parent / "index.html")


def to_unix(ts):
    """Convert various timestamp representations from SQLite to unix seconds (int)."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return int(ts)
    if isinstance(ts, bytes):
        ts = ts.decode('utf-8')

    if isinstance(ts, str):
        s = ts.strip()
        if s.isdigit():
            return int(s)
        try:
            return int(float(s))
        except ValueError:
            pass
        try:
            return int(datetime.fromisoformat(s).timestamp())
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return int(datetime.strptime(s, fmt).timestamp())
            except ValueError:
                continue

    try:
        return int(ts)
    except (ValueError, TypeError):
        raise ValueError(f"Cannot parse timestamp value: {ts!r}")


def _load_sensor_data(cutoff: int, end_ts: int) -> dict[str, list[dict]]:
    """Load sensor data from all DBs within time window."""
    sensors = {}

    if not DATA_DIR.exists():
        return sensors

    for db_path in sorted(DATA_DIR.glob("*.db")):
        sensor_name = _reverse_mac_map.get(db_path.stem.lower(), db_path.stem)
        sensors[sensor_name] = []

        try:
            with sqlite3.connect(str(db_path)) as conn:
                rows = conn.execute("SELECT timestamp, temp, humidity FROM readings ORDER BY timestamp")
                points = []
                for ts, temp, hum in rows:
                    try:
                        t_unix = to_unix(ts)
                        if t_unix and cutoff <= t_unix <= end_ts:
                            points.append({"t": int(t_unix), "temp": temp, "hum": hum})
                    except ValueError:
                        continue
                sensors[sensor_name] = points
                logging.info("Sensor %s: %d points", sensor_name, len(points))
        except Exception as e:
            logging.warning("Error reading DB %s: %s", db_path, e)

    return sensors


def _aggregate_sensor_data(sensors: dict[str, list[dict]], cutoff: int, end_ts: int) -> dict[str, list[dict]]:
    """Aggregate sensor data if total points exceed threshold."""
    all_ts = {p['t'] for pts in sensors.values() for p in pts}

    if not all_ts or len(all_ts) <= DESIRED_POINTS:
        return sensors

    logging.info("Aggregating %d unique timestamps to ~%d points", len(all_ts), DESIRED_POINTS)

    span = max(1, end_ts - cutoff)
    bin_seconds = math.ceil(span / DESIRED_POINTS)

    # Choose rounding unit: day, hour, minute, or second
    unit_seconds = next((u for u in (86400, 3600, 60, 1) if bin_seconds >= u), 1)

    aggregated = {}
    for sensor_name, pts in sensors.items():
        if not pts:
            aggregated[sensor_name] = []
            continue

        # Group points into time bins
        bins = defaultdict(list)
        for p in pts:
            bin_idx = (p['t'] - cutoff) // bin_seconds
            bins[bin_idx].append(p)

        # Aggregate each bin and round timestamp
        agg = []
        for bin_idx in sorted(bins.keys()):
            group = bins[bin_idx]
            avg_t = sum(x['t'] for x in group) // len(group)
            rounded_t = round(avg_t / unit_seconds) * unit_seconds

            if cutoff <= rounded_t <= end_ts:
                avg_temp = sum(float(x['temp']) for x in group) / len(group)
                avg_hum = sum(float(x['hum']) for x in group) / len(group)
                agg.append({"t": int(rounded_t), "temp": round(avg_temp, 3), "hum": int(round(avg_hum))})

        aggregated[sensor_name] = agg
        logging.info("Sensor %s aggregated: %d → %d points", sensor_name, len(pts), len(agg))

    return aggregated


@app.get("/api/readings")
def readings(days: int = 10, end: int | None = None):
    """Get sensor readings for specified time window, with automatic aggregation."""
    end_ts = int(time.time() if end is None else end)
    cutoff = end_ts - days * 86400

    sensors = _load_sensor_data(cutoff, end_ts)
    sensors = _aggregate_sensor_data(sensors, cutoff, end_ts)

    logging.info("Final sensors: %s", list(sensors.keys()))
    return sensors


@app.get("/api/sensors_info")
def sensors_info(days: int = 10, end: int | None = None):
    """Return counts of points per sensor before and after aggregation (for debugging)."""
    end_ts = int(time.time() if end is None else end)
    cutoff = end_ts - days * 86400

    # Get pre-aggregation counts
    sensors_raw = _load_sensor_data(cutoff, end_ts)
    pre_counts = {name: len(pts) for name, pts in sensors_raw.items()}

    # Get post-aggregation counts
    sensors_agg = _aggregate_sensor_data(sensors_raw, cutoff, end_ts)
    post_counts = {name: len(pts) for name, pts in sensors_agg.items()}

    return {"pre": pre_counts, "post": post_counts}
