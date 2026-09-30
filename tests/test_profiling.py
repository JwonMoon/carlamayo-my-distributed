import csv
import time
from pathlib import Path

from module import profiling
from module.run_dir import RunDir


def _rows(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def test_csv_recorder_writes_header_and_rows_in_order(tmp_path):
    rec = profiling.CsvRecorder(tmp_path / "x.csv", ["a", "b"])
    rec.put({"a": 1, "b": 2.5, "ignored": 9})
    rec.put({"a": True})
    rec.close()
    rows = _rows(tmp_path / "x.csv")
    assert rows == [{"a": "1", "b": "2.5"}, {"a": "1", "b": ""}]
    assert rec.rows_written == 2


def test_csv_recorder_keeps_epoch_and_small_durations_precise(tmp_path):
    rec = profiling.CsvRecorder(tmp_path / "t.csv", ["wall_time", "dt"])
    rec.put({"wall_time": 1759259000.123456, "dt": 0.000123})
    rec.put({"wall_time": 1759259000.623456, "dt": 1.5})
    rec.close()
    rows = _rows(tmp_path / "t.csv")
    assert rows[0]["wall_time"] == "1759259000.123456" and rows[1]["wall_time"] == "1759259000.623456"
    assert rows[0]["dt"] == "0.000123" and rows[1]["dt"] == "1.5"


def test_csv_recorder_appends_without_duplicate_header(tmp_path):
    path = tmp_path / "x.csv"
    r1 = profiling.CsvRecorder(path, ["a"]); r1.put({"a": 1}); r1.close()
    r2 = profiling.CsvRecorder(path, ["a"]); r2.put({"a": 2}); r2.close()
    assert path.read_text().count("a\n") == 1
    assert [r["a"] for r in _rows(path)] == ["1", "2"]


def test_system_sampler_collects_cpu_ram_and_net():
    sampler = profiling.SystemSampler(lambda: None, interval_sec=0.05)
    first = sampler.sample()
    time.sleep(0.05)
    second = sampler.sample()
    assert {"wall_time", "cpu_percent", "rss_mb", "ram_used_mb"} <= set(first)
    assert "net_sent_bps" in second and second["net_sent_bps"] >= 0
    assert "gpu_util" in second  # empty string without a GPU, a number with one


def test_client_profiler_writes_three_files(tmp_path):
    run = RunDir.create("closed", "1.5", "normal", root=tmp_path)
    prof = profiling.ClientProfiler(run, interval_sec=0.05)
    prof.tick(frame=1, tick_sec=0.01, speed_kmh=3.2, has_trajectory=False)
    prof.rpc({"kind": "predict", "request_id": "r1", "rtt_sec": 0.5, "status": "OK"})
    time.sleep(0.2)
    prof.close()
    ticks = _rows(run.path("profile_client.csv"))
    assert ticks[0]["frame"] == "1" and ticks[0]["speed_kmh"] == "3.2" and ticks[0]["has_trajectory"] == "0"
    rpcs = _rows(run.path("profile_client_rpc.csv"))
    assert rpcs[0]["request_id"] == "r1" and rpcs[0]["status"] == "OK" and rpcs[0]["wall_time"]
    assert len(_rows(run.path("profile_client_sys.csv"))) >= 1


def test_client_profiler_disabled_writes_nothing(tmp_path):
    run = RunDir.create("open", "2", root=tmp_path)
    prof = profiling.ClientProfiler(run, enabled=False)
    prof.tick(frame=1)
    prof.rpc({"kind": "predict"})
    prof.close()
    assert not Path(run.path("profile_client.csv")).exists()


def test_server_profiler_splits_files_by_run_id(tmp_path):
    prof = profiling.ServerProfiler(tmp_path / "runs", interval_sec=0.05)
    prof.on_request({"run_id": "run-a", "kind": "predict", "request_id": "1", "total_sec": 0.1, "status": "OK"})
    prof.on_request({"run_id": "run-b", "kind": "vqa", "request_id": "2", "total_sec": 0.2, "status": "OK"})
    prof.on_request({"run_id": "../evil", "kind": "predict", "request_id": "3", "status": "OK"})
    time.sleep(0.2)
    prof.close()
    assert _rows(tmp_path / "runs/run-a/profile_server.csv")[0]["request_id"] == "1"
    assert _rows(tmp_path / "runs/run-b/profile_server.csv")[0]["kind"] == "vqa"
    assert (tmp_path / "runs/evil/profile_server.csv").exists()
    assert not (tmp_path / "evil").exists()
    # system samples go to whichever run is active (the last one seen)
    assert len(_rows(tmp_path / "runs/evil/profile_server_sys.csv")) >= 1
