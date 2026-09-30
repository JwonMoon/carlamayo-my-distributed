"""Shared helpers for the CARLA loop runners."""

import os
import time

import numpy as np

from module import config as cfg
from module.profiling import ClientProfiler


def collect_oom_kwargs(args):
    """Gather the optional OOM-free tuning knobs set on the parsed args."""
    oom_kwargs = {}
    if getattr(args, "oom_free_headroom_gb", None) is not None:
        oom_kwargs["headroom_gb"] = args.oom_free_headroom_gb
    if getattr(args, "oom_free_margin", None) is not None:
        oom_kwargs["margin"] = args.oom_free_margin
    if getattr(args, "oom_free_resident", None) is not None:
        oom_kwargs["resident_override"] = args.oom_free_resident
    return oom_kwargs


def derive_pygame_ui_video_path(output_video_path):
    """Return the companion video path for recorded Pygame UI frames."""
    root, ext = os.path.splitext(output_video_path)
    return f"{root}_pygame_ui{ext or '.mp4'}"


def trajectory_is_stale(trajectory_ts, now=None, max_age_sec=None):
    """True when the trajectory computed at ``trajectory_ts`` is older than the limit.

    ``None`` timestamps (no trajectory yet) and a non-positive limit never count as stale.
    """
    if trajectory_ts is None:
        return False
    if max_age_sec is None:
        max_age_sec = cfg.TRAJECTORY_MAX_AGE_SEC
    if max_age_sec is None or max_age_sec <= 0:
        return False
    if now is None:
        now = time.time()
    return (now - float(trajectory_ts)) > float(max_age_sec)


def trajectory_max_age_sec(args):
    value = getattr(args, "trajectory_max_age_sec", None)
    return cfg.TRAJECTORY_MAX_AGE_SEC if value is None else float(value)


def start_client_profiler(adapter, args):
    """Create the run's :class:`ClientProfiler` and route remote RPC timings into it."""
    profiler = ClientProfiler(
        getattr(args, "run_dir", None),
        interval_sec=getattr(args, "profile_interval_sec", None) or cfg.PROFILE_INTERVAL_SEC,
        enabled=getattr(args, "profile", True),
    )
    if profiler.enabled and getattr(adapter, "is_remote", False):
        adapter.on_rpc = profiler.rpc
    return profiler


def record_local_inference(profiler, adapter, kind, frame, inference_sec, error=None):
    """Local adapters have no RPC; log their inference time on the same CSV as RPCs."""
    if getattr(adapter, "is_remote", False):
        return  # the remote adapter already reported through on_rpc
    profiler.rpc({
        "kind": kind, "request_id": f"local-{frame}", "frame_submitted": frame,
        "rtt_sec": inference_sec, "inference_sec": inference_sec,
        "status": "OK" if error is None else "ERROR", "error": error or "",
    })


def stack_frame_buffer(frame_buffer, num_cameras):
    """Stack a rolling camera frame buffer into a ``(cam, frame, H, W, C)`` array."""
    images_array = np.zeros(
        (num_cameras, cfg.NUM_FRAMES, cfg.IMG_HEIGHT, cfg.IMG_WIDTH, cfg.IMG_CHANNELS),
        dtype=np.uint8,
    )
    for t, frame_images in enumerate(frame_buffer):
        for c in range(num_cameras):
            images_array[c, t] = frame_images[c]
    return images_array
