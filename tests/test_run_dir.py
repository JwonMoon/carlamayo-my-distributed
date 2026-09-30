import argparse
import json
from datetime import datetime
from pathlib import Path

from module import run_dir as rd


def test_build_run_id_format_and_sanitizing():
    now = datetime(2026, 10, 1, 14, 30, 22)
    assert rd.build_run_id("closed", "1.5", "navigation", "cfg 1.5!", now=now) == (
        "20261001-143022_closed_v1.5_navigation_cfg-1.5"
    )
    assert rd.build_run_id("open", "2", now=now) == "20261001-143022_open_v2"
    assert rd.build_run_id("live-open", "1", None, "   ", now=now) == "20261001-143022_live-open_v1"


def test_create_makes_unique_folders(tmp_path):
    now = datetime(2026, 10, 1, 14, 30, 22)
    first = rd.RunDir.create("closed", "1.5", "normal", root=tmp_path, now=now)
    second = rd.RunDir.create("closed", "1.5", "normal", root=tmp_path, now=now)
    assert first.path_.is_dir() and second.path_.is_dir()
    assert first.run_id == "20261001-143022_closed_v1.5_normal"
    assert second.run_id == "20261001-143022_closed_v1.5_normal-2"


def test_path_keeps_explicit_directories(tmp_path):
    run = rd.RunDir.create("open", "2", root=tmp_path)
    assert run.path("video.mp4") == str(run.path_ / "video.mp4")
    assert run.path("/abs/video.mp4") == "/abs/video.mp4"
    assert run.path("sub/video.mp4") == "sub/video.mp4"


def test_write_args_records_metadata(tmp_path):
    run = rd.RunDir.create("closed", "1.5", "vqa", tag="t1", root=tmp_path)
    args = argparse.Namespace(version="1.5", mode="vqa", run_dir=run, async_mode=True)
    out = run.write_args(args, extra={"loop": "closed"})
    data = json.loads(Path(out).read_text())
    assert data["run_id"] == run.run_id
    assert data["loop"] == "closed"
    assert data["args"] == {"version": "1.5", "mode": "vqa", "async_mode": True}
    assert "run_dir" not in data["args"]
    assert {"started_at", "hostname", "git_sha", "argv"} <= set(data)


def test_start_log_mirrors_stdout(tmp_path, capsys):
    run = rd.RunDir.create("open", "1", root=tmp_path)
    run.start_log()
    print("hello run")
    run.close()
    assert "hello run" in (run.path_ / "log.txt").read_text()
    assert "hello run" in capsys.readouterr().out


def test_resolve_output_video_with_and_without_run_dir(tmp_path):
    run = rd.RunDir.create("closed", "1.5", "normal", root=tmp_path)
    with_run = argparse.Namespace(output_video=None, run_dir=run)
    assert rd.resolve_output_video(with_run, "default.mp4") == str(run.path_ / "default.mp4")
    named = argparse.Namespace(output_video="mine.mp4", run_dir=run)
    assert rd.resolve_output_video(named, "default.mp4") == str(run.path_ / "mine.mp4")
    no_run = argparse.Namespace(output_video=None)
    assert rd.resolve_output_video(no_run, "default.mp4") == "default.mp4"
    legacy = argparse.Namespace(output_video="x.mp4", run_dir=None)
    assert rd.resolve_output_video(legacy, "default.mp4") == "x.mp4"
