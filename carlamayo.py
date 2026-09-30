# SPDX-FileCopyrightText: Copyright (c) 2026 AVEES Lab
# SPDX-License-Identifier: Apache-2.0
#
# Unified CARLA + Alpamayo launcher: pick an Alpamayo version and a loop mode.

"""CarlaMayo unified entrypoint.

Select the Alpamayo release with ``--version {1,1.5,2}`` and the CARLA loop with
``--loop {open,closed,live-open}``:

* ``open``       Replay a recorded dataset through the model (offline, no driving).
* ``closed``     The model drives the ego vehicle via a PID follower.
* ``live-open``  CARLA autopilot drives; the model runs live and is observed open-loop.

The thin ``carlamayo_open_loop.py`` / ``carlamayo_closed_loop.py`` scripts call this
module with a preset loop for backward compatibility.
"""

import argparse

from module.adapters import SUPPORTED_VERSIONS, get_adapter, normalize_version
from module.run_dir import DEFAULT_RUNS_ROOT, RunDir

IMAGE_ENCODINGS = ("jpeg", "raw_rgb8")
SERVER_ONLY_FLAGS = ("quantization", "oom_free", "oom_free_headroom_gb", "oom_free_margin",
                     "oom_free_resident")

LOOPS = ("open", "closed", "live-open")


def build_parser(preset_loop=None):
    parser = argparse.ArgumentParser(
        description="Run CARLA + Alpamayo in open / closed / live-open loop.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--version",
        dest="version",
        required=True,
        choices=SUPPORTED_VERSIONS,
        help="Alpamayo model version to run (required).",
    )
    if preset_loop is None:
        parser.add_argument(
            "--loop",
            required=True,
            choices=LOOPS,
            help="CARLA loop mode.",
        )

    # Shared model-loading options.
    parser.add_argument(
        "--quantization", dest="quantization", action="store_true",
        help="Use 4-bit quantized model instead of full precision.",
    )
    parser.add_argument(
        "--oom-free", dest="oom_free", action="store_true",
        help="Use OOM-free CPU<->GPU demand layering (Alpamayo 1.5 only).",
    )
    parser.add_argument("--oom-free-headroom-gb", type=float, default=None,
                        help="OOM-free: VRAM (GB) reserved for activation spikes.")
    parser.add_argument("--oom-free-margin", type=int, default=None,
                        help="OOM-free: safety margin subtracted from resident VLM layers.")
    parser.add_argument("--oom-free-resident", type=int, default=None,
                        help="OOM-free: force this many GPU-resident VLM layers.")
    parser.add_argument("--device-map", default="auto",
                        help='Model device_map passed to from_pretrained.')
    parser.add_argument("--cuda-linalg-library", choices=("default", "cusolver", "magma"),
                        default="magma", help="Preferred CUDA linalg backend.")
    parser.add_argument("--output-video", default=None,
                        help="Output video name. A bare name is written inside the run folder.")

    # Per-run output folder: runs/<timestamp>_<loop>_v<version>[_<mode>][_<tag>]/
    parser.add_argument("--runs-root", default=DEFAULT_RUNS_ROOT,
                        help="Parent directory for per-run output folders.")
    parser.add_argument("--run-tag", default=None,
                        help="Optional suffix appended to the run folder name.")
    parser.add_argument("--no-run-dir", action="store_true",
                        help="Write outputs to the current directory like upstream did.")

    # Remote inference (two-host setup): send frames to alpamayo_server.py instead of
    # loading the model in this process. Model-loading flags then belong to the server.
    parser.add_argument("--inference-server", default=None, metavar="HOST:PORT",
                        help="Alpamayo inference server address, e.g. 172.31.20.213:50051.")
    parser.add_argument("--image-encoding", choices=IMAGE_ENCODINGS, default="jpeg",
                        help="[remote] How camera frames are sent. raw_rgb8 is for parity checks.")
    parser.add_argument("--jpeg-quality", type=int, default=95,
                        help="[remote] JPEG quality when --image-encoding jpeg.")
    parser.add_argument("--rpc-timeout-sec", type=float, default=120.0,
                        help="[remote] Deadline for one Predict/AnswerQuestion call.")
    parser.add_argument("--rpc-connect-timeout-sec", type=float, default=30.0,
                        help="[remote] How long to wait for the server to be reachable and warmed up.")

    # CARLA connection (override to run alongside other simulators on one host).
    parser.add_argument("--carla-host", default="localhost", help="CARLA server host.")
    parser.add_argument("--carla-port", type=int, default=2000, help="CARLA RPC port.")
    parser.add_argument("--tm-port", type=int, default=8000,
                        help="CARLA Traffic Manager port.")

    # Open-loop options.
    parser.add_argument("--data-root", default="carla_data",
                        help="[open] Dataset root with trajectory.json and camera folders.")

    # Closed-loop / live-open options.
    parser.add_argument("--async", dest="async_mode", action="store_true",
                        help="[closed, live-open] Non-blocking background inference worker.")
    parser.add_argument("--pygame-ui", action="store_true",
                        help="[closed] Pygame camera UI with prompt input and pause/resume.")
    parser.add_argument("--mode", choices=("normal", "navigation", "vqa"), default="normal",
                        help="[closed] Inference mode.")
    parser.add_argument("--navigation-text", default="",
                        help='[closed, live-open] Navigation instruction (1.5 / 2 only).')
    parser.add_argument("--navigation-weight", type=float, default=1.0,
                        help="[closed] Navigation CFG weight (1.5 only for CFG).")
    parser.add_argument("--vqa-question", default="",
                        help="[closed] Initial VQA question for --mode vqa.")
    parser.add_argument("--debug-worker-traceback", action="store_true",
                        help="[closed, live-open] Print async worker tracebacks on failure.")
    return parser


def main(argv=None, preset_loop=None):
    parser = build_parser(preset_loop=preset_loop)
    args = parser.parse_args(argv)
    loop = preset_loop or args.loop

    args.run_dir = None if args.no_run_dir else create_run_dir(args, loop)
    adapter = build_adapter(args, parser)

    try:
        if loop == "open":
            from module.loops import open_loop

            open_loop.run(adapter, args)
        elif loop == "closed":
            from module.loops import closed_loop

            closed_loop.run(adapter, args)
        elif loop == "live-open":
            from module.loops import live_open_loop

            live_open_loop.run(adapter, args)
        else:  # pragma: no cover - argparse restricts choices
            parser.error(f"Unknown loop {loop!r}")
    finally:
        if args.run_dir is not None:
            args.run_dir.close()


def build_adapter(args, parser=None):
    """Local model adapter, or a remote proxy when --inference-server is given.

    The remote adapter does not connect here; ``load_model()`` inside the loop does.
    """
    if not args.inference_server:
        return get_adapter(args.version)

    used = [f for f in SERVER_ONLY_FLAGS if getattr(args, f, None)]
    if args.device_map != "auto":
        used.append("device_map")
    if used:
        message = (
            "--inference-server is set, but these options configure model loading and "
            f"belong to alpamayo_server.py on the inference host: {', '.join('--' + f.replace('_', '-') for f in used)}"
        )
        if parser is not None:
            parser.error(message)
        raise SystemExit(message)

    from module.remote.client import RemoteAlpamayoAdapter

    run_dir = getattr(args, "run_dir", None)
    return RemoteAlpamayoAdapter(
        args.inference_server,
        expected_version=args.version,
        image_encoding=args.image_encoding,
        jpeg_quality=args.jpeg_quality,
        rpc_timeout_sec=args.rpc_timeout_sec,
        connect_timeout_sec=args.rpc_connect_timeout_sec,
        run_id=run_dir.run_id if run_dir is not None else "",
    )


def create_run_dir(args, loop):
    """Create the per-run output folder, start the stdout log and save the arguments."""
    mode = args.mode if loop == "closed" else None
    run_dir = RunDir.create(
        loop=loop, version=normalize_version(args.version) or args.version, mode=mode,
        tag=args.run_tag, root=args.runs_root,
    )
    run_dir.start_log()
    run_dir.write_args(args, extra={"loop": loop})
    print(f"Run folder: {run_dir}  (run_id={run_dir.run_id})")
    return run_dir


if __name__ == "__main__":
    main()
