from datetime import datetime, date
import pandas as pd


TEST_DATE = date(2025, 12, 25)

METER_READINGS = pd.DataFrame({
    "timestamp": [
        datetime(2025, 12, 25, 14, 0, 0),
        datetime(2025, 12, 25, 14, 1, 0),
        datetime(2025, 12, 25, 14, 2, 0),
        datetime(2025, 12, 25, 14, 3, 0),
        datetime(2025, 12, 25, 14, 4, 0),
    ],
    "temp": [19.9, 20.0, 20.1, 20.2, 20.1],
    "humidity": [45, 46, 47, 49, 51]
})
