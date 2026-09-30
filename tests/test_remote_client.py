import numpy as np
import pytest

from module import config as cfg
from module.inference import extract_trajectory_samples, select_trajectory_by_prev_similarity
from module.remote import codec
from module.remote import server as srv
from module.remote.client import RemoteAlpamayoAdapter, RemoteInferenceError
from module.remote.fake_adapter import FakeAdapter
from module.vlm_generate_optimization import VlmGenerateTiming

H, W = 24, 32


def _images(fill=7):
    return np.full((4, cfg.NUM_FRAMES, H, W, 3), fill, dtype=np.uint8)


def _history():
    xyz = np.arange(cfg.NUM_HISTORY * 3, dtype=np.float32).reshape(cfg.NUM_HISTORY, 3) * 0.1
    rot = np.tile(np.eye(3, dtype=np.float32), (cfg.NUM_HISTORY, 1, 1))
    return xyz, rot


@pytest.fixture
def server(tmp_path):
    started = []

    def _start(adapter=None, **kw):
        adapter = adapter or FakeAdapter()
        model, processor = adapter.load_model()
        kw.setdefault("runs_root", tmp_path / "runs")
        servicer = srv.AlpamayoServicer(adapter, model, processor, **kw)
        grpc_server, port = srv.create_server(servicer, host="127.0.0.1", port=0)
        grpc_server.start()
        started.append(grpc_server)
        return servicer, f"127.0.0.1:{port}"

    yield _start
    for s in started:
        s.stop(grace=None)


def _client(target, **kw):
    kw.setdefault("expected_version", "fake")
    kw.setdefault("connect_timeout_sec", 3.0)
    kw.setdefault("rpc_timeout_sec", 5.0)
    return RemoteAlpamayoAdapter(target, **kw)


def test_load_model_copies_rig_and_capabilities(server):
    _, target = server()
    remote = _client(target, run_id="run-x")
    assert remote.source_camera_configs == {}
    model, processor = remote.load_model()
    assert (model, processor) == (None, None)
    assert remote.source_camera_configs == FakeAdapter.source_camera_configs
    assert remote.source_camera_indices == FakeAdapter.source_camera_indices
    assert remote.viz_camera_slot == FakeAdapter.viz_camera_slot
    assert remote.num_cameras == 4
    assert (remote.supports_navigation, remote.supports_vqa, remote.supports_oom_free) == (True, True, False)
    assert remote.version == "fake" and remote.model_id == "carlamayo/fake"
    assert "remote" in remote.display_name and "Fake" in remote.display_name
    assert "Remote inference" in remote.runtime_summary()
    remote.close()


@pytest.mark.parametrize("encoding", [codec.ENCODING_RAW, codec.ENCODING_JPEG])
def test_run_inference_roundtrip_feeds_the_loop_helpers(server, encoding):
    servicer, target = server()
    remote = _client(target, image_encoding=encoding, run_id="run-1")
    remote.load_model()
    xyz, rot = _history()
    timing = VlmGenerateTiming()

    data = remote.prepare_model_input(_images(), xyz, rot, 500_000)
    data["meta"] = {"frame": 12, "prompt_revision": 3, "respawn_revision": 1}
    pred_xyz, extra = remote.run_inference(
        None, None, data, navigation_text="Turn left", navigation_weight=1.5,
        vlm_generate_timing=timing, seed=42,
    )

    expected = FakeAdapter.expected_trajectory(xyz, 500_000, "Turn left", 42, image_mean=7.0)
    assert isinstance(pred_xyz, np.ndarray) and pred_xyz.dtype == np.float32
    np.testing.assert_allclose(pred_xyz, expected, atol=1e-6)
    assert remote.extract_cot_text(extra) == "fake cot nav='Turn left' weight=1.50"
    assert timing.calls == 1
    # the exact helpers closed_loop.py applies to the result:
    samples = extract_trajectory_samples(pred_xyz)
    assert samples.shape == (1, 64, 3)
    idx, _ = select_trajectory_by_prev_similarity(samples, None)
    assert idx == 0
    # request metadata reached the server and came back in the profile record
    assert extra["frame_submitted"] == 12 and extra["rtt_sec"] > 0
    assert extra["request_bytes"] > 0 and extra["response_bytes"] > 0
    assert servicer.adapter.calls[-1] == ("predict", "Turn left", 1.5, 42)


def test_run_vqa_roundtrip(server):
    _, target = server()
    remote = _client(target)
    remote.load_model()
    xyz, rot = _history()
    data = remote.prepare_model_input(_images(), xyz, rot, 1)
    extra = remote.run_vqa(None, None, data, question="What is ahead?")
    assert remote.extract_answer_text(extra) == "fake answer to: What is ahead?"
    assert extra["raw_answer"] == "<raw>What is ahead?</raw>"


def test_version_mismatch_is_rejected_at_handshake(server):
    _, target = server()
    remote = _client(target, expected_version="1.5")
    with pytest.raises(RemoteInferenceError, match="serves Alpamayo 'fake'"):
        remote.load_model()


def test_config_mismatch_is_rejected(server, monkeypatch):
    _, target = server()
    original = srv.build_model_info

    def server_with_other_config(*a, **kw):
        info = original(*a, **kw)
        info.num_frames = cfg.NUM_FRAMES + 1  # the server host runs a different config.py
        return info

    monkeypatch.setattr(srv, "build_model_info", server_with_other_config)
    remote = _client(target)
    with pytest.raises(RemoteInferenceError, match="NUM_FRAMES"):
        remote.load_model()


def test_client_adopts_server_sample_count_instead_of_rejecting(server, monkeypatch):
    _, target = server()
    original = srv.build_model_info

    def server_with_more_samples(*a, **kw):
        info = original(*a, **kw)
        info.num_traj_samples = 8  # set with alpamayo_server.py --num-traj-samples 8
        return info

    monkeypatch.setattr(srv, "build_model_info", server_with_more_samples)
    remote = _client(target)
    remote.load_model()  # no FAILED_PRECONDITION
    assert remote.num_traj_samples == 8
    assert "traj_samples=8" in remote.runtime_summary()


def test_unreachable_server_fails_fast():
    remote = _client("127.0.0.1:1", connect_timeout_sec=0.5)
    with pytest.raises(RemoteInferenceError, match="no inference server"):
        remote.load_model()


def test_not_warmed_up_server_times_out_with_clear_message(server):
    _, target = server(warmed_up=False)
    remote = _client(target, connect_timeout_sec=0.5)
    with pytest.raises(RemoteInferenceError, match="not warmed up"):
        remote.load_model()


def test_deadline_maps_to_remote_error_and_records_status(server):
    _, target = server(adapter=FakeAdapter(sleep_sec=1.0))
    records = []
    remote = _client(target, rpc_timeout_sec=0.2, on_rpc=records.append)
    remote.load_model()
    xyz, rot = _history()
    data = remote.prepare_model_input(_images(), xyz, rot, 1)
    with pytest.raises(RemoteInferenceError) as err:
        remote.run_inference(None, None, data)
    assert err.value.code == "DEADLINE_EXCEEDED"
    assert records[-1]["status"] == "DEADLINE_EXCEEDED"


def test_prepare_before_load_is_an_error(server):
    _, target = server()
    remote = _client(target)
    xyz, rot = _history()
    with pytest.raises(RemoteInferenceError, match="load_model"):
        remote.prepare_model_input(_images(), xyz, rot, 1)


def test_wrong_camera_count_is_rejected_client_side(server):
    _, target = server()
    remote = _client(target)
    remote.load_model()
    xyz, rot = _history()
    with pytest.raises(ValueError, match="expects \\(4"):
        remote.prepare_model_input(np.zeros((7, cfg.NUM_FRAMES, H, W, 3), dtype=np.uint8), xyz, rot, 1)
