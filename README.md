# switchbot_meter

## Start service
source venv/bin/activate  

Raspberry Pi:
uvicorn iot_monitor.api.main:app --host 0.0.0.0 --port 8000

Windows:
uvicorn src.api.dashboard_api:app --host 0.0.0.0 --port 8000 --reload


## systemd
[Unit]
Description=IoT Dashboard
After=network.target

[Service]
User=pi  
WorkingDirectory=/opt/iot-dashboard  
ExecStart=/opt/iot-dashboard/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target