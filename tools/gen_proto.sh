#!/usr/bin/env bash
# Regenerate the gRPC Python stubs from module/remote/alpamayo_inference.proto.
# Run from the repository root; needs `pip install grpcio-tools`.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m grpc_tools.protoc -I . \
  --python_out=. --grpc_python_out=. --pyi_out=. \
  module/remote/alpamayo_inference.proto
echo "generated module/remote/alpamayo_inference_pb2*.py"
