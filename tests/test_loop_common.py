import argparse

from module import config as cfg
from module.loops import _common
from module.remote.fake_adapter import FakeAdapter
from module.run_dir import RunDir


def test_trajectory_is_stale_rules():
    assert _common.trajectory_is_stale(None, now=100.0, max_age_sec=3.0) is False
    assert _common.trajectory_is_stale(98.0, now=100.0, max_age_sec=3.0) is False
    assert _common.trajectory_is_stale(96.0, now=100.0, max_age_sec=3.0) is True
    assert _common.trajectory_is_stale(0.0, now=100.0, max_age_sec=0) is False  # disabled
    assert _common.trajectory_is_stale(0.0, now=100.0, max_age_sec=None) is (100.0 > cfg.TRAJECTORY_MAX_AGE_SEC)


def test_trajectory_max_age_from_args_or_config():
    assert _common.trajectory_max_age_sec(argparse.Namespace()) == cfg.TRAJECTORY_MAX_AGE_SEC
    assert _common.trajectory_max_age_sec(argparse.Namespace(trajectory_max_age_sec=2.5)) == 2.5
    assert _common.trajectory_max_age_sec(argparse.Namespace(trajectory_max_age_sec=0)) == 0.0


def test_start_client_profiler_routes_remote_rpcs(tmp_path):
    run = RunDir.create("closed", "1.5", "normal", root=tmp_path)
    remote_like = FakeAdapter()
    remote_like.is_remote = True
    args = argparse.Namespace(run_dir=run, profile=True, profile_interval_sec=0.05)
    profiler = _common.start_client_profiler(remote_like, args)
    assert profiler.enabled and remote_like.on_rpc == profiler.rpc
    _common.record_local_inference(profiler, remote_like, "predict", 1, 0.5)  # ignored for remote
    profiler.close()
    assert not (run.path_ / "profile_client_rpc.csv").read_text().strip().count("\n")


def test_record_local_inference_writes_rpc_row(tmp_path):
    run = RunDir.create("closed", "1.5", "normal", root=tmp_path)
    args = argparse.Namespace(run_dir=run, profile=True, profile_interval_sec=0.05)
    profiler = _common.start_client_profiler(FakeAdapter(), args)
    _common.record_local_inference(profiler, FakeAdapter(), "predict", 7, 1.25)
    _common.record_local_inference(profiler, FakeAdapter(), "vqa", 8, 0.0, error="boom")
    profiler.close()
    lines = (run.path_ / "profile_client_rpc.csv").read_text().strip().splitlines()
    assert len(lines) == 3 and "local-7" in lines[1] and "ERROR" in lines[2]


def test_profiler_disabled_without_run_dir():
    profiler = _common.start_client_profiler(FakeAdapter(), argparse.Namespace())
    assert profiler.enabled is False
    profiler.tick(frame=1)
    profiler.close()
