import csv
import time

import numpy as np
import pytest

import alpamayo_server
from module import config as cfg
from module.remote import server as srv
from module.remote.client import RemoteAlpamayoAdapter, RemoteInferenceError


def test_parser_defaults():
    args = alpamayo_server.build_parser().parse_args(["--version", "1.5"])
    assert args.version == "1.5" and args.fake is False
    assert (args.host, args.port) == ("0.0.0.0", srv.DEFAULT_PORT)
    assert args.max_message_mb == srv.DEFAULT_MAX_MESSAGE_MB
    assert args.profile is True and args.runs_root == "runs"
    assert args.no_warmup is False and args.device_map == "auto"


def test_num_traj_samples_flag_overrides_config_and_is_advertised(tmp_path, monkeypatch):
    import grpc

    from module import config as cfg
    from module.remote import alpamayo_inference_pb2 as pb
    from module.remote import alpamayo_inference_pb2_grpc as pb_grpc

    monkeypatch.setattr(cfg, "NUM_TRAJ_SAMPLES", 1)
    args = alpamayo_server.build_parser().parse_args(
        ["--fake", "--host", "127.0.0.1", "--port", "0", "--num-traj-samples", "4",
         "--runs-root", str(tmp_path), "--no-profile"]
    )
    assert alpamayo_server.apply_server_config(args) == 4
    assert cfg.NUM_TRAJ_SAMPLES == 4
    server, port, servicer = alpamayo_server.build_server(args)
    server.start()
    try:
        stub = pb_grpc.AlpamayoInferenceStub(grpc.insecure_channel(f"127.0.0.1:{port}"))
        info = stub.GetModelInfo(pb.GetModelInfoRequest())
        assert info.num_traj_samples == 4
    finally:
        server.stop(grace=None)

    bad = alpamayo_server.build_parser().parse_args(["--fake", "--num-traj-samples", "0"])
    with pytest.raises(SystemExit, match=">= 1"):
        alpamayo_server.apply_server_config(bad)


def test_version_required_without_fake():
    args = alpamayo_server.build_parser().parse_args([])
    with pytest.raises(SystemExit, match="--version is required"):
        alpamayo_server.load_adapter(args)


def test_fake_server_end_to_end_with_remote_adapter(tmp_path):
    args = alpamayo_server.build_parser().parse_args(
        ["--fake", "--host", "127.0.0.1", "--port", "0", "--runs-root", str(tmp_path / "runs"),
         "--profile-interval-sec", "0.05"]
    )
    server, port, servicer = alpamayo_server.build_server(args)
    server.start()
    try:
        target = f"127.0.0.1:{port}"
        # Not serving until warm-up: the client waits, then gives up with a clear error.
        early = RemoteAlpamayoAdapter(target, expected_version="fake", connect_timeout_sec=0.3)
        with pytest.raises(RemoteInferenceError, match="not warmed up"):
            early.load_model()

        alpamayo_server.warm_up(servicer.adapter, servicer.model, servicer.processor)
        srv.set_serving(servicer, True)

        remote = RemoteAlpamayoAdapter(target, expected_version="fake", run_id="cli-run", connect_timeout_sec=3)
        remote.load_model()
        assert remote.num_cameras == 4
        images = np.zeros((4, cfg.NUM_FRAMES, 8, 8, 3), dtype=np.uint8)
        xyz = np.zeros((cfg.NUM_HISTORY, 3), dtype=np.float32)
        rot = np.tile(np.eye(3, dtype=np.float32), (cfg.NUM_HISTORY, 1, 1))
        pred, extra = remote.run_inference(None, None, remote.prepare_model_input(images, xyz, rot, 0))
        assert pred.shape == (1, 1, 1, 64, 3)
        assert extra["cot"].startswith("fake cot")
        remote.close()
    finally:
        srv.set_serving(servicer, False)
        server.stop(grace=None)
        servicer.profiler.close()

    run_folder = tmp_path / "runs" / "cli-run"
    assert (run_folder / "server_info.json").exists()
    with open(run_folder / "profile_server.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows and rows[0]["status"] == "OK" and rows[0]["kind"] == "predict"


def test_warm_up_uses_config_shapes():
    from module.remote.fake_adapter import FakeAdapter

    adapter = FakeAdapter()
    model, processor = adapter.load_model()
    t0 = time.perf_counter()
    alpamayo_server.warm_up(adapter, model, processor)
    assert adapter.calls[-1][0] == "predict"
    assert time.perf_counter() - t0 < 30
