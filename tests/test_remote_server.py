import threading
import time

import grpc
import numpy as np
import pytest

from module import config as cfg
from module.remote import alpamayo_inference_pb2 as pb
from module.remote import alpamayo_inference_pb2_grpc as pb_grpc
from module.remote import codec
from module.remote import server as srv
from module.remote.fake_adapter import FakeAdapter

H, W = 24, 32


def _images(cams=4, frames=cfg.NUM_FRAMES, fill=7):
    return np.full((cams, frames, H, W, 3), fill, dtype=np.uint8)


def _history():
    xyz = np.arange(cfg.NUM_HISTORY * 3, dtype=np.float32).reshape(cfg.NUM_HISTORY, 3) * 0.1
    rot = np.tile(np.eye(3, dtype=np.float32), (cfg.NUM_HISTORY, 1, 1))
    return xyz, rot


def _predict_request(run_id="run-1", nav="", weight=1.0, seed=None, encoding=codec.ENCODING_RAW, frame=5):
    xyz, rot = _history()
    req = pb.PredictRequest(
        meta=pb.ClientMeta(request_id="r1", frame=frame, prompt_revision=2, respawn_revision=1, run_id=run_id),
        images=codec.encode_image_stack(_images(), encoding),
        history_xyz=codec.array_to_tensor(xyz),
        history_rot=codec.array_to_tensor(rot),
        t0_us=500_000,
        navigation_text=nav,
        navigation_weight=weight,
    )
    if seed is not None:
        req.seed = seed
    return req


@pytest.fixture
def make_server(tmp_path):
    started = []

    def _start(adapter=None, **servicer_kwargs):
        adapter = adapter or FakeAdapter()
        model, processor = adapter.load_model()
        servicer_kwargs.setdefault("runs_root", tmp_path / "runs")
        servicer = srv.AlpamayoServicer(adapter, model, processor, **servicer_kwargs)
        server, port = srv.create_server(servicer, host="127.0.0.1", port=0)
        server.start()
        channel = grpc.insecure_channel(f"127.0.0.1:{port}", options=srv.grpc_channel_options())
        started.append((server, channel))
        return servicer, pb_grpc.AlpamayoInferenceStub(channel), port

    yield _start
    for server, channel in started:
        channel.close()
        server.stop(grace=None)


def test_model_info_reports_rig_config_and_capabilities(make_server):
    _, stub, _ = make_server()
    info = stub.GetModelInfo(pb.GetModelInfoRequest(client_protocol_version=srv.PROTOCOL_VERSION))
    assert info.protocol_version == srv.PROTOCOL_VERSION
    assert info.version == "fake" and info.display_name == "Fake Alpamayo"
    assert [c.name for c in info.cameras] == list(FakeAdapter.source_camera_configs)
    assert list(info.camera_indices) == list(FakeAdapter.source_camera_indices)
    assert info.viz_camera_slot == FakeAdapter.viz_camera_slot
    assert (info.supports_navigation, info.supports_vqa, info.supports_oom_free) == (True, True, False)
    assert (info.num_frames, info.num_history) == (cfg.NUM_FRAMES, cfg.NUM_HISTORY)
    assert (info.img_height, info.img_width) == (cfg.IMG_HEIGHT, cfg.IMG_WIDTH)
    assert info.num_traj_samples == cfg.NUM_TRAJ_SAMPLES
    assert info.warmed_up is True
    assert set(info.image_encodings) == set(codec.IMAGE_ENCODINGS)


def test_model_info_rejects_other_protocol(make_server):
    _, stub, _ = make_server()
    with pytest.raises(grpc.RpcError) as err:
        stub.GetModelInfo(pb.GetModelInfoRequest(client_protocol_version="999"))
    assert err.value.code() == grpc.StatusCode.FAILED_PRECONDITION


@pytest.mark.parametrize("encoding", [codec.ENCODING_RAW, codec.ENCODING_JPEG])
def test_predict_roundtrip_matches_adapter_output(make_server, encoding):
    servicer, stub, _ = make_server()
    req = _predict_request(nav="Turn right in 30m", weight=1.5, seed=42, encoding=encoding)
    resp = stub.Predict(req)

    xyz, _ = _history()
    pred = codec.tensor_to_array(resp.pred_xyz)
    assert pred.shape == (1, 1, 1, 64, 3) and pred.dtype == np.float32
    expected = FakeAdapter.expected_trajectory(xyz, 500_000, "Turn right in 30m", 42, image_mean=7.0)
    np.testing.assert_allclose(pred, expected, rtol=0, atol=1e-6)
    assert resp.cot_text == "fake cot nav='Turn right in 30m' weight=1.50"
    assert resp.meta.request_id == "r1" and resp.meta.frame == 5
    assert (resp.meta.prompt_revision, resp.meta.respawn_revision) == (2, 1)
    assert resp.meta.run_id == "run-1"
    assert resp.timings.total_sec > 0 and resp.timings.inference_sec >= 0
    assert resp.timings.vlm_generate_calls == 1
    assert servicer.adapter.calls[-1] == ("predict", "Turn right in 30m", 1.5, 42)


def test_predict_without_seed_passes_none(make_server):
    servicer, stub, _ = make_server()
    stub.Predict(_predict_request())
    assert servicer.adapter.calls[-1] == ("predict", "", 1.0, None)


def test_vqa_roundtrip(make_server):
    servicer, stub, _ = make_server()
    xyz, rot = _history()
    req = pb.VqaRequest(
        meta=pb.ClientMeta(request_id="q1", run_id="run-1"),
        images=codec.encode_image_stack(_images(), codec.ENCODING_JPEG),
        history_xyz=codec.array_to_tensor(xyz),
        history_rot=codec.array_to_tensor(rot),
        t0_us=1,
        question="What is ahead?",
    )
    resp = stub.AnswerQuestion(req)
    assert resp.answer == "fake answer to: What is ahead?"
    assert resp.raw_answer == "<raw>What is ahead?</raw>"
    assert servicer.adapter.calls[-1] == ("vqa", "What is ahead?", None)


def test_server_mirrors_run_folder_once(make_server, tmp_path):
    _, stub, _ = make_server()
    stub.Predict(_predict_request(run_id="20261001-120000_closed_v1.5_normal"))
    stub.Predict(_predict_request(run_id="20261001-120000_closed_v1.5_normal"))
    run_path = tmp_path / "runs" / "20261001-120000_closed_v1.5_normal"
    assert (run_path / "server_info.json").exists()
    # A run_id that tries to escape runs_root is ignored, not created.
    stub.Predict(_predict_request(run_id="../escape"))
    assert not (tmp_path / "escape").exists()


def test_on_request_hook_receives_timing_record(make_server):
    records = []
    _, stub, _ = make_server(on_request=records.append)
    stub.Predict(_predict_request())
    assert len(records) == 1
    rec = records[0]
    assert rec["kind"] == "predict" and rec["status"] == "OK" and rec["run_id"] == "run-1"
    assert rec["request_bytes"] > 0 and rec["total_sec"] > 0
    assert {"decode_sec", "prepare_sec", "inference_sec", "gpu_mem_peak_mb"} <= set(rec)


def test_not_warmed_up_is_failed_precondition(make_server):
    servicer, stub, _ = make_server(warmed_up=False)
    with pytest.raises(grpc.RpcError) as err:
        stub.Predict(_predict_request())
    assert err.value.code() == grpc.StatusCode.FAILED_PRECONDITION
    srv.set_serving(servicer, True)
    assert stub.Predict(_predict_request()).cot_text


def test_bad_payload_is_invalid_argument(make_server):
    _, stub, _ = make_server()
    req = _predict_request()
    req.images.num_frames = 3  # 16 frames carried, 12 declared
    with pytest.raises(grpc.RpcError) as err:
        stub.Predict(req)
    assert err.value.code() == grpc.StatusCode.INVALID_ARGUMENT


def test_adapter_exception_is_internal_and_lock_is_released(make_server):
    records = []
    _, stub, _ = make_server(adapter=FakeAdapter(fail_with=RuntimeError("boom")), on_request=records.append)
    with pytest.raises(grpc.RpcError) as err:
        stub.Predict(_predict_request())
    assert err.value.code() == grpc.StatusCode.INTERNAL and "boom" in err.value.details()
    assert records[-1]["status"] == "INTERNAL"
    # a second call must not hang on a leaked lock
    with pytest.raises(grpc.RpcError):
        stub.Predict(_predict_request())


def test_concurrent_request_is_refused(make_server):
    _, stub, _ = make_server(adapter=FakeAdapter(sleep_sec=1.0))
    results = {}

    def first():
        results["first"] = stub.Predict(_predict_request())

    t = threading.Thread(target=first)
    t.start()
    time.sleep(0.3)
    with pytest.raises(grpc.RpcError) as err:
        stub.Predict(_predict_request())
    assert err.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
    t.join()
    assert results["first"].cot_text


def test_client_deadline_maps_to_deadline_exceeded(make_server):
    _, stub, _ = make_server(adapter=FakeAdapter(sleep_sec=1.0))
    with pytest.raises(grpc.RpcError) as err:
        stub.Predict(_predict_request(), timeout=0.2)
    assert err.value.code() == grpc.StatusCode.DEADLINE_EXCEEDED


def test_cusolver_fallback_retries_once(monkeypatch):
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("CUSOLVER_STATUS_INTERNAL_ERROR happened")
        return "ok"

    monkeypatch.setattr(srv, "configure_cuda_linalg_library", lambda lib: calls.append(lib))
    assert srv.AlpamayoServicer._run_with_linalg_fallback(flaky) == "ok"
    assert calls == [1, "magma", 1]
    with pytest.raises(RuntimeError, match="other"):
        srv.AlpamayoServicer._run_with_linalg_fallback(lambda: (_ for _ in ()).throw(RuntimeError("other")))
