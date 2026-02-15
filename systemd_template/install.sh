#!/usr/bin/env bash
set -euo pipefail

# Installs both:
# - switchbot-api.service (always-on API)
# - switchbot-collector.service + switchbot-collector.timer (daily collector)

DEST_DIR="/etc/systemd/system"
TEMPLATE_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing systemd units to ${DEST_DIR}"

install_unit() {
  local unit_name="$1"
  sudo install -m 0644 "${TEMPLATE_DIR}/${unit_name}" "${DEST_DIR}/${unit_name}"
}

# --- API (always-on) ---
install_unit "switchbot-api.service"

# --- Collector (timer) ---
install_unit "switchbot-collector.service"
install_unit "switchbot-collector.timer"

sudo systemctl daemon-reload

# Enable/start the always-on API
sudo systemctl enable --now switchbot-api.service

# Enable/start the daily collector timer
sudo systemctl enable --now switchbot-collector.timer

echo
echo "Done. Status:"
systemctl status switchbot-api.service --no-pager || true
systemctl status switchbot-collector.timer --no-pager || true

echo
echo "Next collector runs:"
systemctl list-timers --all | grep "switchbot-collector" || true
