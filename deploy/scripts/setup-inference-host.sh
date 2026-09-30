#!/usr/bin/env bash
# One-time setup for the inference host (B): uv env, Alpamayo 1.5 submodule, gRPC deps.
set -euo pipefail
REPO="${REPO:-$HOME/carlamayo}"
VERSION_DIR="${ALPAMAYO_SUBMODULE:-third_party/alpamayo1.5}"

sudo apt-get update
sudo apt-get install -y rsync
cd "$REPO"
git submodule update --init "$VERSION_DIR"

if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv venv a_venv --python 3.12
# shellcheck disable=SC1091
source a_venv/bin/activate
uv sync --active || uv sync --active --no-install-package flash-attn
# uv-managed Pythons ship without ensurepip/pip: use `uv pip` inside the venv.
uv pip install --no-deps -e "$VERSION_DIR"
uv pip install -r requirements-inference.txt
python -c "import alpamayo1_5, grpc, cv2, bitsandbytes, psutil; print('inference deps OK')"
echo "inference host ready. Next: hf auth login, then"
echo "  python alpamayo_server.py --version 1.5 --host <private-ip> --port 50051"
