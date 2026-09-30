#!/usr/bin/env bash
# Copy carla_data/ from the sim host to the inference host (for open-loop path 1).
#   deploy/scripts/sync-dataset-to-inference-host.sh [user@host] [remote_repo_dir]
set -euo pipefail
HOST="${1:-${INFERENCE_HOST:-ubuntu@172.31.20.213}}"
REMOTE_REPO="${2:-${REMOTE_REPO:-~/carlamayo}}"
DATA="${DATA_ROOT:-carla_data}"
cd "$(dirname "$0")/../.."
rsync -avz --progress "$DATA/" "$HOST:$REMOTE_REPO/$DATA/"
echo "synced $DATA/ -> $HOST:$REMOTE_REPO/$DATA/"
