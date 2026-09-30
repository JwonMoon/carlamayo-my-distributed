#!/usr/bin/env python
"""Compare open-loop predictions of two runs (parity check: local vs remote, raw vs JPEG).

    python tools/compare_predictions.py runs/<local_run> runs/<remote_run>

Each run folder must contain ``predictions.npz`` (written by ``--loop open``). Prints a
per-frame table of the max absolute difference and the mean per-waypoint distance, plus
the overall numbers; exits non-zero when ``--atol`` is exceeded.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


def load_predictions(run_dir: Path) -> dict:
    path = run_dir / "predictions.npz"
    if not path.exists():
        raise SystemExit(f"{path} not found (run --loop open with a run folder first)")
    data = np.load(path, allow_pickle=True)
    return {
        "predictions": data["predictions"],
        "frame_ids": data["frame_ids"],
        "inference_times": data["inference_times"],
        "seed": int(data["seed"]) if "seed" in data else None,
    }


def compare(a: dict, b: dict) -> dict:
    n = min(len(a["frame_ids"]), len(b["frame_ids"]))
    if n == 0:
        raise SystemExit("no frames to compare")
    if not np.array_equal(a["frame_ids"][:n], b["frame_ids"][:n]):
        raise SystemExit("runs cover different frames; compare runs of the same dataset")
    pa, pb = a["predictions"][:n], b["predictions"][:n]
    if pa.shape != pb.shape:
        raise SystemExit(f"prediction shapes differ: {pa.shape} vs {pb.shape}")
    max_abs = np.abs(pa - pb).reshape(n, -1).max(axis=1)
    per_wp = np.linalg.norm(pa[..., :2] - pb[..., :2], axis=-1).reshape(n, -1).mean(axis=1)
    return {
        "frames": n,
        "frame_ids": a["frame_ids"][:n],
        "max_abs": max_abs,
        "mean_xy_dist": per_wp,
        "overall_max_abs": float(max_abs.max()),
        "overall_mean_xy_dist": float(per_wp.mean()),
        "bitwise_identical": bool(np.array_equal(pa, pb)),
        "inference_time_a": float(np.mean(a["inference_times"][:n])),
        "inference_time_b": float(np.mean(b["inference_times"][:n])),
    }


def format_report(name_a: str, name_b: str, result: dict) -> str:
    lines = [f"# Prediction parity: `{name_a}` vs `{name_b}`", "",
             "| frame | max |a-b| | mean xy dist (m) |", "|---|---|---|"]
    for fid, m, d in zip(result["frame_ids"], result["max_abs"], result["mean_xy_dist"]):
        lines.append(f"| {int(fid)} | {m:.3g} | {d:.3g} |")
    lines += ["",
              f"- frames compared: {result['frames']}",
              f"- bitwise identical: {result['bitwise_identical']}",
              f"- overall max |a-b|: {result['overall_max_abs']:.3g}",
              f"- overall mean xy distance: {result['overall_mean_xy_dist']:.3g} m",
              f"- mean inference time: {result['inference_time_a']:.3f} s vs {result['inference_time_b']:.3f} s",
              ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_a")
    parser.add_argument("run_b")
    parser.add_argument("--atol", type=float, default=1e-4, help="fail if max |a-b| exceeds this")
    parser.add_argument("--out", default=None, help="write the report here (default: run_b/parity.md)")
    args = parser.parse_args(argv)
    run_a, run_b = Path(args.run_a), Path(args.run_b)
    result = compare(load_predictions(run_a), load_predictions(run_b))
    report = format_report(run_a.name, run_b.name, result)
    out = Path(args.out) if args.out else run_b / "parity.md"
    out.write_text(report)
    print(report)
    print(f"written {out}")
    return 0 if result["overall_max_abs"] <= args.atol else 2


if __name__ == "__main__":
    sys.exit(main())
