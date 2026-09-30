# SPDX-FileCopyrightText: Copyright (c) 2026 AVEES Lab
# SPDX-License-Identifier: Apache-2.0
#
# Alpamayo inference server for the two-host (CARLA host / inference host) setup.

"""Serve one Alpamayo version over gRPC so ``carlamayo.py --inference-server`` can use it.

Run this on the inference host (the machine with the GPU and the model weights):

    python alpamayo_server.py --version 1.5 --host 172.31.20.213 --port 50051

Model-loading options (``--quantization``, ``--oom-free``, ``--device-map``) live here;
the CARLA-side client only sends camera frames and receives trajectories. The model is
loaded once, warmed up with a dummy request (so the first real request does not pay
for kernel compilation) and then kept resident until the process exits.

``--fake`` serves the deterministic :class:`FakeAdapter` without any GPU, to verify the
network path, security groups and the client flags before the real model is ready.
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
import time

import numpy as np

from module import config as cfg
from module.adapters import SUPPORTED_VERSIONS, get_adapter
from module.loops._common import collect_oom_kwargs
from module.remote import server as srv


def build_parser():
    parser = argparse.ArgumentParser(
        description="Serve an Alpamayo model to remote CARLA clients over gRPC.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--version", dest="version", choices=SUPPORTED_VERSIONS,
                        help="Alpamayo model version to serve (required unless --fake).")
    parser.add_argument("--fake", action="store_true",
                        help="Serve a GPU-free fake adapter for connectivity tests.")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Interface to bind. Use the private IP on AWS (e.g. 172.31.20.213).")
    parser.add_argument("--port", type=int, default=srv.DEFAULT_PORT, help="gRPC port (0 = any free).")
    parser.add_argument("--max-message-mb", type=int, default=srv.DEFAULT_MAX_MESSAGE_MB,
                        help="Max gRPC message size; raw 7-camera stacks need ~200 MB.")
    parser.add_argument("--max-workers", type=int, default=4,
                        help="gRPC worker threads (model calls are serialized regardless).")

    # Model loading (same options carlamayo.py has for the single-host case).
    parser.add_argument("--quantization", action="store_true", help="4-bit quantized model.")
    parser.add_argument("--oom-free", dest="oom_free", action="store_true",
                        help="OOM-free CPU<->GPU demand layering (Alpamayo 1.5 only).")
    parser.add_argument("--oom-free-headroom-gb", type=float, default=None)
    parser.add_argument("--oom-free-margin", type=int, default=None)
    parser.add_argument("--oom-free-resident", type=int, default=None)
    parser.add_argument("--device-map", default="auto", help="device_map for from_pretrained.")
    parser.add_argument("--cuda-linalg-library", choices=("default", "cusolver", "magma"),
                        default="magma")
    parser.add_argument("--no-warmup", action="store_true",
                        help="Skip the dummy warm-up inference after loading.")

    # Per-run mirroring and profiling (see docs/distributed-architecture.md §9).
    parser.add_argument("--runs-root", default="runs",
                        help="Where runs/<run_id>/ folders from clients are mirrored.")
    parser.add_argument("--profile", dest="profile", action="store_true", default=True,
                        help="Record per-request timings to runs/<run_id>/profile_server.csv.")
    parser.add_argument("--no-profile", dest="profile", action="store_false")
    parser.add_argument("--profile-interval-sec", type=float, default=1.0,
                        help="System resource sampling period for profile_server_sys.csv.")
    return parser


def load_adapter(args):
    """Return ``(adapter, model, processor)`` for the requested version (or the fake)."""
    if args.fake:
        from module.remote.fake_adapter import FakeAdapter

        adapter = FakeAdapter(version="fake")
        model, processor = adapter.load_model(use_quantization=args.quantization)
        return adapter, model, processor

    if not args.version:
        raise SystemExit("--version is required (or pass --fake).")
    adapter = get_adapter(args.version)
    if args.oom_free and not adapter.supports_oom_free:
        raise SystemExit(f"{adapter.display_name} does not support --oom-free.")
    if args.oom_free and args.quantization:
        raise SystemExit("--oom-free and --quantization are mutually exclusive.")

    from module.inference import configure_cuda_linalg_library

    configure_cuda_linalg_library(args.cuda_linalg_library)
    print(f"Loading {adapter.display_name} ({adapter.model_id})...")
    t0 = time.perf_counter()
    model, processor = adapter.load_model(
        use_quantization=args.quantization,
        device_map=args.device_map,
        oom_free=args.oom_free,
        oom_kwargs=collect_oom_kwargs(args),
    )
    print(f"Model loaded in {time.perf_counter() - t0:.0f}s. {adapter.runtime_summary()}")
    return adapter, model, processor


def warm_up(adapter, model, processor):
    """One dummy inference so CUDA kernels / flash-attn are compiled before clients arrive."""
    images = np.zeros(
        (adapter.num_cameras, cfg.NUM_FRAMES, cfg.IMG_HEIGHT, cfg.IMG_WIDTH, cfg.IMG_CHANNELS),
        dtype=np.uint8,
    )
    history_xyz = np.zeros((cfg.NUM_HISTORY, 3), dtype=np.float32)
    history_rot = np.tile(np.eye(3, dtype=np.float32), (cfg.NUM_HISTORY, 1, 1))
    t0 = time.perf_counter()
    data = adapter.prepare_model_input(images, history_xyz, history_rot, 0)
    adapter.run_inference(model, processor, data)
    print(f"Warm-up inference done in {time.perf_counter() - t0:.1f}s.")


def build_server(args, adapter=None, model=None, processor=None):
    """Create servicer + gRPC server (not started). Returns ``(server, port, servicer)``."""
    if adapter is None:
        adapter, model, processor = load_adapter(args)

    profiler = None
    if args.profile:
        from module.profiling import ServerProfiler

        profiler = ServerProfiler(args.runs_root, interval_sec=args.profile_interval_sec)

    servicer = srv.AlpamayoServicer(
        adapter, model, processor,
        warmed_up=False,
        device_map=args.device_map,
        runs_root=args.runs_root,
        on_request=profiler.on_request if profiler is not None else None,
    )
    servicer.profiler = profiler
    server, port = srv.create_server(
        servicer, host=args.host, port=args.port,
        max_message_mb=args.max_message_mb, max_workers=args.max_workers,
    )
    return server, port, servicer


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    server, port, servicer = build_server(args)
    server.start()
    print(f"gRPC server listening on {args.host}:{port} (not serving until warm-up completes)")

    if args.no_warmup:
        print("Warm-up skipped (--no-warmup).")
    else:
        warm_up(servicer.adapter, servicer.model, servicer.processor)
    srv.set_serving(servicer, True)
    print(
        f"SERVING {servicer.adapter.display_name} version={servicer.adapter.version} "
        f"warmed_up=True cameras={servicer.adapter.num_cameras} "
        f"NUM_FRAMES={cfg.NUM_FRAMES} IMG={cfg.IMG_WIDTH}x{cfg.IMG_HEIGHT}"
    )
    print(f"Clients: python carlamayo.py --loop closed --version {servicer.adapter.version} "
          f"--inference-server <this-host-ip>:{port}")

    stop = threading.Event()

    def _shutdown(signum, _frame):
        print(f"\nSignal {signum}: stopping server...")
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _shutdown)
    try:
        while not stop.is_set():
            stop.wait(1.0)
    finally:
        srv.set_serving(servicer, False)
        server.stop(grace=5.0)
        if getattr(servicer, "profiler", None) is not None:
            servicer.profiler.close()
        print(f"Stopped. Requests served: {servicer.requests_served}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
