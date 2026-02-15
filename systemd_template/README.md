# systemd template (Raspberry Pi)

This folder contains unit file templates to run the collector on a schedule using a **systemd timer**, and to run the API as a long-running **systemd service**.

Files:

Collector (scheduled):
- `switchbot-collector.service` — one-shot collector run (Type=oneshot)
- `switchbot-collector.timer` — daily schedule for the service

API (always-on):
- `switchbot-api.service` — runs the dashboard API continuously (recommended)
- `switchbot-api-reload.service` — same but with `--reload` (development only)

Utilities:
- `install.sh` — helper installer script (optional)

> Important: before installing, verify paths in `ExecStart` and `WorkingDirectory`.
