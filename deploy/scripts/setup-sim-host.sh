#!/usr/bin/env bash
# One-time setup for the CARLA sim host (A): CARLA 0.9.16 + torch-free Python env.
set -euo pipefail
REPO="${REPO:-$HOME/carlamayo}"
CARLA_DIR="${CARLA_ROOT:-$HOME/carla}"

sudo apt-get update
sudo apt-get install -y python3.10 python3.10-venv ffmpeg libvulkan1 rsync netcat-openbsd

if [ ! -f "$CARLA_DIR/CarlaUE4.sh" ]; then
  mkdir -p "$CARLA_DIR" && cd "$CARLA_DIR"
  wget -q --show-progress https://tiny.carla.org/carla-0-9-16-linux -O carla-0.9.16.tar.gz
  tar -xzf carla-0.9.16.tar.gz && rm carla-0.9.16.tar.gz
fi
grep -q "CARLA_ROOT" "$HOME/.bashrc" || echo "export CARLA_ROOT=$CARLA_DIR" >> "$HOME/.bashrc"

cd "$REPO"
python3.10 -m venv venv-sim
# shellcheck disable=SC1091
source venv-sim/bin/activate
pip install --upgrade pip
pip install -r requirements-sim.txt || {
  echo "carla wheel not on PyPI for this Python? try:"
  echo "  pip install $CARLA_DIR/PythonAPI/carla/dist/carla-0.9.16-*.whl"
}
echo "sim host ready: source $REPO/venv-sim/bin/activate; export CARLA_ROOT=$CARLA_DIR"
