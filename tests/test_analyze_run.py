import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

from module import profiling
from module.run_dir import RunDir

ROOT = Path(__file__).resolve().parents[1]
pytest.importorskip("pandas")


def _load_tool():
    spec = importlib.util.spec_from_file_location("analyze_run", ROOT / "tools" / "analyze_run.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["analyze_run"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_run(root, name, remote=True, n=6):
    run = RunDir.create("closed", "1.5", name, root=root)
    run.write_args(
        type("A", (), {"__dict__": {}})(),
        extra={"loop": "closed", "args": {"mode": name, "async_mode": True,
                                          "inference_server": "h:1" if remote else None,
                                          "image_encoding": "jpeg"}},
    )
    (run.path_ / "args.json").write_text(json.dumps({
        "run_id": run.run_id, "loop": "closed", "started_at": "x", "hostname": "h", "git_sha": "abc",
        "args": {"mode": name, "async_mode": True, "inference_server": "h:1" if remote else None,
                 "image_encoding": "jpeg", "version": "1.5"},
    }))
    prof = profiling.ClientProfiler(run, interval_sec=0.02)
    t0 = time.time()
    for i in range(n * 4):
        prof.tick(frame=i, sim_time=i * 0.1, wall_time=t0 + i * 0.1, tick_sec=0.05 + 0.01 * (i % 3),
                  camera_capture_sec=0.01, inference_sec=0.0, control_sec=0.002, ui_sec=0.001,
                  speed_kmh=10 + i, steer=0.0, throttle=0.3, brake=0.0,
                  trajectory_age_sec=0.5 + 0.1 * (i % 5), pending_inference=False, has_trajectory=True)
    for i in range(n):
        prof.rpc({"wall_time": t0 + i, "kind": "predict", "request_id": f"r{i}", "frame_submitted": i * 4,
                  "encode_sec": 0.1, "image_bytes": 5_000_000, "request_bytes": 5_100_000,
                  "response_bytes": 900, "rtt_sec": 1.2 + 0.1 * i, "server_total_sec": 1.0 + 0.1 * i,
                  "inference_sec": 0.9 + 0.1 * i, "status": "OK" if i else "DEADLINE_EXCEEDED"})
    time.sleep(0.1)
    prof.close()
    sprof = profiling.ServerProfiler(root, interval_sec=0.02)
    for i in range(n):
        sprof.on_request({"recv_wall_time": t0 + i, "kind": "predict", "request_id": f"r{i}",
                          "run_id": run.run_id, "frame": i * 4, "request_bytes": 5_100_000,
                          "decode_sec": 0.05, "prepare_sec": 0.02, "inference_sec": 0.9 + 0.1 * i,
                          "vlm_generate_sec": 0.5, "total_sec": 1.0 + 0.1 * i,
                          "gpu_mem_allocated_mb": 22000, "gpu_mem_peak_mb": 24000 + i, "status": "OK"})
    time.sleep(0.1)
    sprof.close()
    (run.path_ / "server_info.json").write_text(json.dumps({"version": "1.5", "model_id": "m"}))
    return run


def test_summary_and_plots(tmp_path):
    tool = _load_tool()
    run = _make_run(tmp_path, "normal")
    summary = tool.analyze(run.path_)
    text = summary.read_text()
    assert text.startswith(f"# Run summary: `{run.run_id}`")
    for section in ("## Headline", "Client: per tick", "Client: per RPC", "Client: system",
                    "Server: per request", "Server: system", "## Plots"):
        assert section in text
    assert "| rtt_sec |" in text and "| gpu_mem_peak_mb |" in text
    assert "Status counts: OK=5, DEADLINE_EXCEEDED=1" in text
    assert "| overhead_mean_s |" in text
    plots = sorted(p.name for p in (run.path_ / "plots").glob("*.png"))
    assert {"inference_time.png", "rtt.png", "server_breakdown.png", "gpu_mem.png", "cpu.png",
            "trajectory_age.png", "speed.png"} <= set(plots)


def test_summary_without_server_files_and_without_plots(tmp_path):
    tool = _load_tool()
    run = _make_run(tmp_path, "vqa", remote=False)
    for name in ("profile_server.csv", "profile_server_sys.csv", "server_info.json"):
        (run.path_ / name).unlink()
    summary = tool.analyze(run.path_, plots=False)
    text = summary.read_text()
    assert "_(file missing or empty)_" in text
    assert not (run.path_ / "plots").exists()
    head = tool.headline_metrics(tool.load_run(run.path_))
    assert head["encoding"] == "local" and head["requests"] == 6 and head["errors"] == 1
    assert head["sim_realtime_ratio"] > 0


def test_compare_runs_writes_table(tmp_path):
    tool = _load_tool()
    a = _make_run(tmp_path, "normal")
    b = _make_run(tmp_path, "navigation")
    out = tmp_path / "compare.md"
    text = tool.compare_runs([a.path_, b.path_], out)
    assert out.exists() and text.startswith("# Run comparison")
    assert a.run_id in text and b.run_id in text and "rtt_p95_s" in text


def test_cli_entrypoint_defaults_to_summary(tmp_path, capsys):
    tool = _load_tool()
    run = _make_run(tmp_path, "normal")
    assert tool.main([str(run.path_), "--no-plots"]) == 0
    assert "written" in capsys.readouterr().out
    assert tool.main(["compare", str(run.path_), "--out", str(tmp_path / "c.md")]) == 0
    assert (tmp_path / "c.md").exists()
