# switchbot_meter

## Start service
source venv/bin/activate  

### Collector

python -m src.collector.main

### API

Raspberry Pi:
uvicorn src.api.dashboard_api:app --host 0.0.0.0 --port 8000

Windows:
uvicorn src.api.dashboard_api:app --host 0.0.0.0 --port 8000 --reload


## Dahsboard

prod: http://192.168.1.117:8000  
local test: http://localhost:8000


## systemd
This repo includes ready-to-use systemd unit templates under `systemd_template/`.

### Run the API continuously (always-on)
Use `switchbot-api.service` to run the dashboard API continuously and let systemd restart it on failures.

> Important: edit the template before installing. If you see `status=217/USER`, it means the `User=` in the unit file does not exist on your system.

1) Copy templates to Raspberry Pi

```bash
scp -r systemd_template user@<RASPBERRY_IP>:/home/user/
```

2) Edit placeholders in the service file
Open `/home/user/systemd_template/switchbot-api.service` and replace:
- `User=__USER__` with your actual username (e.g. `pi` or `user`)
- `WorkingDirectory=__PROJECT_DIR__` with your repo path (e.g. `/home/user/workspace/sensors`)
- `ExecStart=__PROJECT_DIR__/venv/bin/uvicorn ...` (same repo path)

3) Install and enable the API service

```bash
sudo install -m 0644 /home/user/systemd_template/switchbot-api.service /etc/systemd/system/switchbot-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now switchbot-api.service
```

4) Check status and logs

```bash
systemctl status switchbot-api.service --no-pager
journalctl -u switchbot-api.service -n 200 --no-pager
```

The dashboard should be available from your LAN at:
- `http://<RASPBERRY_IP>:8000/`

> Note: there is also `switchbot-api-reload.service` (development only) which starts Uvicorn with `--reload`.

### Run the collector daily (timer)
They configure a daily collector run using a **systemd timer**.

#### 1) Copy templates to Raspberry Pi
From your local machine (Windows/Linux/macOS) to a folder on Raspberry Pi:

```bash
scp -r systemd_template user@<RASPBERRY_IP>:/home/user/
```

#### 2) Verify paths in the service file
On Raspberry Pi, open `switchbot-collector.service` and verify:
- `WorkingDirectory=/home/user/workspace/sensors`
- `ExecStart=/home/user/workspace/sensors/venv/bin/python -m src.collector.main`
- `User=pi`

If your project/venv path or the collector entry module differs, update them accordingly.

#### 3) Install units and enable the timer
On Raspberry Pi:

Option A (manual):

```bash
sudo install -m 0644 /home/user/systemd_template/switchbot-collector.service /etc/systemd/system/switchbot-collector.service
sudo install -m 0644 /home/user/systemd_template/switchbot-collector.timer /etc/systemd/system/switchbot-collector.timer
sudo systemctl daemon-reload
sudo systemctl enable --now switchbot-collector.timer
```

Option B (script):

```bash
cd /home/user/systemd_template
chmod +x install.sh
./install.sh
```

#### 4) Verify
Timer status and next runs:

```bash
systemctl status switchbot-collector.timer --no-pager
systemctl list-timers --all | grep switchbot-collector
```

Run collector manually (to validate the unit file):

```bash
sudo systemctl start switchbot-collector.service
journalctl -u switchbot-collector.service -n 200 --no-pager
```
