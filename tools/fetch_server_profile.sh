#!/usr/bin/env bash
# Copy the inference host's profile CSVs for one run into the local run folder.
#
#   tools/fetch_server_profile.sh <run_id> [user@host] [remote_repo_dir]
#
# Run on the sim host after a closed/live-open/open-loop run. Defaults match the
# AWS layout in docs/distributed/cheatsheet.md; override with arguments or environment variables
#   INFERENCE_HOST=ubuntu@172.31.20.213  REMOTE_REPO=~/carlamayo  RUNS_ROOT=runs
set -euo pipefail

RUN_ID="${1:?usage: $0 <run_id> [user@host] [remote_repo_dir]}"
HOST="${2:-${INFERENCE_HOST:-ubuntu@172.31.20.213}}"
REMOTE_REPO="${3:-${REMOTE_REPO:-~/carlamayo}}"
RUNS_ROOT="${RUNS_ROOT:-runs}"

cd "$(dirname "$0")/.."
mkdir -p "$RUNS_ROOT/$RUN_ID"
rsync -avz --progress \
  "$HOST:$REMOTE_REPO/$RUNS_ROOT/$RUN_ID/" \
  --include='profile_server*.csv' --include='server_info.json' --exclude='*' \
  "$RUNS_ROOT/$RUN_ID/"
echo "Fetched server profile into $RUNS_ROOT/$RUN_ID/"
ls -la "$RUNS_ROOT/$RUN_ID/" | grep -E 'profile_server|server_info' || true
