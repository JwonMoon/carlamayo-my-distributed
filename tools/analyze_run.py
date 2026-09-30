#!/usr/bin/env python
"""Summarise one run's profiling CSVs (tables + plots) or compare several runs.

    python tools/analyze_run.py runs/<run_id>            # -> summary.md, plots/*.png
    python tools/analyze_run.py runs/<run_id> --no-plots
    python tools/analyze_run.py compare runs/<a> runs/<b> [...]   # -> compare.md (cwd)

Inputs (all optional; whatever exists is used):
    profile_client.csv, profile_client_rpc.csv, profile_client_sys.csv   (sim host)
    profile_server.csv, profile_server_sys.csv                            (inference host,
                                                        fetched with tools/fetch_server_profile.sh)
    args.json, server_info.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

STATS = ["count", "mean", "std", "min", "p50", "p95", "max"]

TICK_COLS = ["tick_sec", "camera_capture_sec", "inference_sec", "control_sec", "ui_sec",
             "speed_kmh", "trajectory_age_sec"]
RPC_COLS = ["encode_sec", "image_bytes", "request_bytes", "response_bytes", "rtt_sec",
            "server_total_sec", "inference_sec", "overhead_sec"]
SERVER_COLS = ["decode_sec", "prepare_sec", "inference_sec", "vlm_generate_sec", "total_sec",
               "request_bytes", "gpu_mem_allocated_mb", "gpu_mem_peak_mb"]
SYS_COLS = ["cpu_percent", "process_cpu_percent", "rss_mb", "ram_used_mb", "gpu_util",
            "gpu_mem_used_mb", "net_sent_bps", "net_recv_bps"]


# ----------------------------------------------------------------------------- io
def read_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    df = pd.read_csv(path)
    if df.empty:
        return None
    for col in df.columns:
        if col not in ("kind", "request_id", "run_id", "status", "error"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_run(run_dir: Path) -> dict:
    data = {
        "run_dir": run_dir,
        "run_id": run_dir.name,
        "ticks": read_csv(run_dir / "profile_client.csv"),
        "rpc": read_csv(run_dir / "profile_client_rpc.csv"),
        "client_sys": read_csv(run_dir / "profile_client_sys.csv"),
        "server": read_csv(run_dir / "profile_server.csv"),
        "server_sys": read_csv(run_dir / "profile_server_sys.csv"),
        "args": _read_json(run_dir / "args.json"),
        "server_info": _read_json(run_dir / "server_info.json"),
    }
    rpc = data["rpc"]
    if rpc is not None and {"rtt_sec", "server_total_sec"} <= set(rpc.columns):
        rpc["overhead_sec"] = rpc["rtt_sec"] - rpc["server_total_sec"].fillna(0.0)
    return data


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------------ stats
def describe(df: pd.DataFrame | None, columns: list[str]) -> pd.DataFrame:
    rows = []
    if df is None:
        return pd.DataFrame(columns=["metric", *STATS])
    for col in columns:
        if col not in df.columns:
            continue
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            continue
        rows.append({
            "metric": col, "count": int(series.count()), "mean": series.mean(),
            "std": series.std(ddof=0), "min": series.min(), "p50": series.quantile(0.5),
            "p95": series.quantile(0.95), "max": series.max(),
        })
    return pd.DataFrame(rows, columns=["metric", *STATS])


def _fmt(value) -> str:
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        if np.isnan(value):
            return ""
        if abs(value) >= 1e5:
            return f"{value:,.0f}"
        return f"{value:.4g}"
    return str(value)


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(no data)_\n"
    header = "| " + " | ".join(df.columns) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    body = ["| " + " | ".join(_fmt(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([header, sep, *body]) + "\n"


def headline_metrics(data: dict) -> dict[str, float | str]:
    """The handful of numbers worth quoting in a report."""
    out: dict[str, float | str] = {"run_id": data["run_id"]}
    args = data.get("args") or {}
    a = args.get("args", {}) if isinstance(args, dict) else {}
    out["loop"] = args.get("loop", "") if isinstance(args, dict) else ""
    out["mode"] = a.get("mode", "")
    out["remote"] = bool(a.get("inference_server"))
    out["async"] = bool(a.get("async_mode"))
    out["encoding"] = a.get("image_encoding", "") if out["remote"] else "local"
    rpc = data["rpc"]
    if rpc is not None:
        ok = rpc[rpc["status"] == "OK"] if "status" in rpc.columns else rpc
        out["requests"] = len(rpc)
        out["errors"] = int(len(rpc) - len(ok))
        for col, name in (("rtt_sec", "rtt_mean_s"), ("inference_sec", "inference_mean_s"),
                          ("overhead_sec", "overhead_mean_s"), ("request_bytes", "request_mb")):
            if col in ok.columns and ok[col].notna().any():
                val = float(ok[col].mean())
                out[name] = val / 1e6 if name == "request_mb" else val
        if "rtt_sec" in ok.columns and ok["rtt_sec"].notna().any():
            out["rtt_p95_s"] = float(ok["rtt_sec"].quantile(0.95))
        if "wall_time" in rpc.columns and "request_bytes" in rpc.columns and len(rpc) > 1:
            span = float(rpc["wall_time"].max() - rpc["wall_time"].min())
            if span > 0:
                out["upload_mbps"] = float(rpc["request_bytes"].sum()) * 8 / span / 1e6
    ticks = data["ticks"]
    if ticks is not None:
        out["ticks"] = len(ticks)
        if "tick_sec" in ticks.columns:
            out["tick_mean_s"] = float(ticks["tick_sec"].mean())
            out["sim_realtime_ratio"] = float(0.1 / max(ticks["tick_sec"].mean(), 1e-9))
        if "trajectory_age_sec" in ticks.columns and ticks["trajectory_age_sec"].notna().any():
            out["traj_age_p95_s"] = float(ticks["trajectory_age_sec"].quantile(0.95))
        if "speed_kmh" in ticks.columns:
            out["speed_mean_kmh"] = float(ticks["speed_kmh"].mean())
    server = data["server"]
    if server is not None:
        if "inference_sec" in server.columns:
            out["server_inference_mean_s"] = float(server["inference_sec"].mean())
        if "gpu_mem_peak_mb" in server.columns and server["gpu_mem_peak_mb"].notna().any():
            out["server_gpu_peak_gb"] = float(server["gpu_mem_peak_mb"].max()) / 1024
    for key, df in (("client", data["client_sys"]), ("server", data["server_sys"])):
        if df is not None:
            if "cpu_percent" in df.columns:
                out[f"{key}_cpu_mean_pct"] = float(df["cpu_percent"].mean())
            if "gpu_mem_used_mb" in df.columns and df["gpu_mem_used_mb"].notna().any():
                out[f"{key}_gpu_mem_max_gb"] = float(df["gpu_mem_used_mb"].max()) / 1024
    return out


# ----------------------------------------------------------------------- report
def write_summary(data: dict, plots: list[Path]) -> Path:
    run_dir: Path = data["run_dir"]
    lines = [f"# Run summary: `{data['run_id']}`", ""]
    args = data.get("args")
    if args:
        lines += ["## Run", "", "| key | value |", "|---|---|"]
        for key in ("loop", "started_at", "hostname", "git_sha"):
            if key in args:
                lines.append(f"| {key} | {args[key]} |")
        for key in ("version", "mode", "async_mode", "inference_server", "image_encoding",
                    "jpeg_quality", "navigation_text", "navigation_weight", "vqa_question", "data_root"):
            if key in args.get("args", {}):
                lines.append(f"| {key} | {args['args'][key]} |")
        lines.append("")
    if data.get("server_info"):
        lines += ["## Server", "", "| key | value |", "|---|---|"]
        for key, value in data["server_info"].items():
            lines.append(f"| {key} | {value} |")
        lines.append("")

    head = headline_metrics(data)
    lines += ["## Headline", "", "| metric | value |", "|---|---|"]
    for key, value in head.items():
        if key != "run_id":
            lines.append(f"| {key} | {_fmt(value)} |")
    lines.append("")

    sections = [
        ("Client: per tick (`profile_client.csv`)", data["ticks"], TICK_COLS),
        ("Client: per RPC (`profile_client_rpc.csv`)", data["rpc"], RPC_COLS),
        ("Client: system (`profile_client_sys.csv`)", data["client_sys"], SYS_COLS),
        ("Server: per request (`profile_server.csv`)", data["server"], SERVER_COLS),
        ("Server: system (`profile_server_sys.csv`)", data["server_sys"], SYS_COLS),
    ]
    for title, df, cols in sections:
        lines += [f"## {title}", ""]
        if df is None:
            lines += ["_(file missing or empty)_", ""]
            continue
        lines.append(markdown_table(describe(df, cols)))
        if "status" in df.columns:
            counts = df["status"].value_counts()
            lines.append("Status counts: " + ", ".join(f"{k}={v}" for k, v in counts.items()) + "\n")
        lines.append("")
    if plots:
        lines += ["## Plots", ""]
        lines += [f"![{p.stem}](plots/{p.name})" for p in plots]
        lines.append("")
    out = run_dir / "summary.md"
    out.write_text("\n".join(lines))
    return out


# ------------------------------------------------------------------------ plots
def make_plots(data: dict) -> list[Path]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed; skipping plots")
        return []

    run_dir: Path = data["run_dir"]
    plots_dir = run_dir / "plots"
    plots_dir.mkdir(exist_ok=True)
    written: list[Path] = []

    def _t(df, col="wall_time"):
        if df is None or col not in df.columns:
            return None
        t0 = df[col].min()
        return df[col] - t0

    def _save(fig, name):
        path = plots_dir / name
        fig.tight_layout()
        fig.savefig(path, dpi=110)
        plt.close(fig)
        written.append(path)

    rpc, server, ticks = data["rpc"], data["server"], data["ticks"]
    csys, ssys = data["client_sys"], data["server_sys"]

    if rpc is not None and "rtt_sec" in rpc.columns:
        fig, ax = plt.subplots(figsize=(9, 3.5))
        ax.plot(_t(rpc), rpc["rtt_sec"], ".-", label="client round trip")
        if "server_total_sec" in rpc.columns:
            ax.plot(_t(rpc), rpc["server_total_sec"], ".-", label="server total")
        if "inference_sec" in rpc.columns:
            ax.plot(_t(rpc), rpc["inference_sec"], ".-", label="model inference")
        ax.set_xlabel("time since first request (s)"); ax.set_ylabel("seconds"); ax.legend()
        ax.set_title("Inference latency per request")
        _save(fig, "inference_time.png")

        fig, ax = plt.subplots(figsize=(9, 3.5))
        if "overhead_sec" in rpc.columns:
            ax.plot(_t(rpc), rpc["overhead_sec"], ".-", label="round trip - server total (network + encode/decode)")
        if "encode_sec" in rpc.columns:
            ax.plot(_t(rpc), rpc["encode_sec"], ".-", label="client JPEG encode")
        ax.set_xlabel("time (s)"); ax.set_ylabel("seconds"); ax.legend(); ax.set_title("Remote overhead")
        _save(fig, "rtt.png")

    if server is not None and {"decode_sec", "prepare_sec", "inference_sec"} <= set(server.columns):
        fig, ax = plt.subplots(figsize=(9, 3.5))
        x = np.arange(len(server))
        bottom = np.zeros(len(server))
        for col in ("decode_sec", "prepare_sec", "inference_sec"):
            ax.bar(x, server[col].fillna(0), bottom=bottom, label=col)
            bottom += server[col].fillna(0).to_numpy()
        ax.set_xlabel("request #"); ax.set_ylabel("seconds"); ax.legend(); ax.set_title("Server time per request")
        _save(fig, "server_breakdown.png")

    if any(df is not None and "gpu_mem_used_mb" in df.columns for df in (csys, ssys)) or (
        server is not None and "gpu_mem_peak_mb" in server.columns
    ):
        fig, ax = plt.subplots(figsize=(9, 3.5))
        if csys is not None and "gpu_mem_used_mb" in csys.columns:
            ax.plot(_t(csys), csys["gpu_mem_used_mb"] / 1024, label="sim host GPU used (CARLA)")
        if ssys is not None and "gpu_mem_used_mb" in ssys.columns:
            ax.plot(_t(ssys), ssys["gpu_mem_used_mb"] / 1024, label="inference host GPU used")
        if server is not None and "gpu_mem_peak_mb" in server.columns and "recv_wall_time" in server.columns:
            ax.plot(_t(server, "recv_wall_time"), server["gpu_mem_peak_mb"] / 1024, ".", label="model peak per request")
        ax.set_xlabel("time (s)"); ax.set_ylabel("GB"); ax.legend(); ax.set_title("GPU memory")
        _save(fig, "gpu_mem.png")

    if any(df is not None and "cpu_percent" in df.columns for df in (csys, ssys)):
        fig, ax = plt.subplots(figsize=(9, 3.5))
        for name, df in (("sim host", csys), ("inference host", ssys)):
            if df is not None and "cpu_percent" in df.columns:
                ax.plot(_t(df), df["cpu_percent"], label=f"{name} CPU %")
        ax.set_xlabel("time (s)"); ax.set_ylabel("%"); ax.legend(); ax.set_title("CPU utilisation")
        _save(fig, "cpu.png")

    if csys is not None and "net_sent_bps" in csys.columns:
        fig, ax = plt.subplots(figsize=(9, 3.5))
        ax.plot(_t(csys), csys["net_sent_bps"] * 8 / 1e6, label="sim host sent (Mbit/s)")
        ax.plot(_t(csys), csys["net_recv_bps"] * 8 / 1e6, label="sim host received (Mbit/s)")
        ax.set_xlabel("time (s)"); ax.set_ylabel("Mbit/s"); ax.legend(); ax.set_title("Network")
        _save(fig, "net.png")

    if ticks is not None and "trajectory_age_sec" in ticks.columns and ticks["trajectory_age_sec"].notna().any():
        fig, ax = plt.subplots(figsize=(9, 3.5))
        ax.plot(ticks["frame"], ticks["trajectory_age_sec"], label="age of followed trajectory")
        ax.set_xlabel("frame"); ax.set_ylabel("seconds"); ax.legend(); ax.set_title("Trajectory age")
        _save(fig, "trajectory_age.png")

    if ticks is not None and "speed_kmh" in ticks.columns:
        fig, ax = plt.subplots(figsize=(9, 3.5))
        ax.plot(ticks["frame"], ticks["speed_kmh"], label="speed (km/h)")
        if "tick_sec" in ticks.columns:
            ax2 = ax.twinx()
            ax2.plot(ticks["frame"], ticks["tick_sec"] * 1000, color="tab:orange", alpha=0.6, label="tick (ms)")
            ax2.set_ylabel("tick ms")
        ax.set_xlabel("frame"); ax.set_ylabel("km/h"); ax.set_title("Ego speed and tick time")
        _save(fig, "speed.png")
    return written


# ---------------------------------------------------------------------- compare
def compare_runs(run_dirs: list[Path], out: Path | None) -> str:
    rows = [headline_metrics(load_run(d)) for d in run_dirs]
    df = pd.DataFrame(rows).fillna("")
    cols = [c for c in ["run_id", "loop", "mode", "remote", "async", "encoding", "requests", "errors",
                        "rtt_mean_s", "rtt_p95_s", "inference_mean_s", "overhead_mean_s",
                        "server_inference_mean_s", "request_mb", "upload_mbps", "tick_mean_s",
                        "sim_realtime_ratio", "traj_age_p95_s", "speed_mean_kmh",
                        "server_gpu_peak_gb", "client_cpu_mean_pct", "server_cpu_mean_pct"] if c in df.columns]
    text = "# Run comparison\n\n" + markdown_table(df[cols])
    if out is not None:
        out.write_text(text)
    return text


# ------------------------------------------------------------------------- main
def analyze(run_dir: Path, plots: bool = True) -> Path:
    data = load_run(run_dir)
    written = make_plots(data) if plots else []
    summary = write_summary(data, written)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command")
    one = sub.add_parser("summary", help="summarise one run (default)")
    one.add_argument("run_dir")
    one.add_argument("--no-plots", action="store_true")
    cmp_ = sub.add_parser("compare", help="compare several runs")
    cmp_.add_argument("run_dirs", nargs="+")
    cmp_.add_argument("--out", default="compare.md")
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ("summary", "compare", "-h", "--help"):
        argv = ["summary", *argv]
    args = parser.parse_args(argv)
    if args.command == "compare":
        text = compare_runs([Path(d) for d in args.run_dirs], Path(args.out))
        print(text)
        print(f"written {args.out}")
        return 0
    if args.command is None:
        parser.print_help()
        return 1
    summary = analyze(Path(args.run_dir), plots=not args.no_plots)
    print(summary.read_text())
    print(f"written {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
