import pytest

import carlamayo


def test_version_and_loop_are_required():
    parser = carlamayo.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["--version", "2"])  # missing --loop
    with pytest.raises(SystemExit):
        parser.parse_args(["--loop", "open"])  # missing --version


def test_invalid_version_and_loop_rejected():
    parser = carlamayo.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--version", "3", "--loop", "open"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--version", "2", "--loop", "sideways"])


def test_preset_loop_drops_loop_flag():
    parser = carlamayo.build_parser(preset_loop="closed")
    args = parser.parse_args(["--version", "1.5"])
    assert args.version == "1.5"
    assert not hasattr(args, "loop")


def test_parsed_defaults_and_overrides():
    parser = carlamayo.build_parser()
    args = parser.parse_args(
        ["--version", "2", "--loop", "live-open", "--async", "--navigation-text", "Turn right"]
    )
    assert args.version == "2"
    assert args.loop == "live-open"
    assert args.async_mode is True
    assert args.navigation_text == "Turn right"
    assert args.mode == "normal"
    assert args.device_map == "auto"
    assert args.output_video is None
    assert args.runs_root == "runs"
    assert args.run_tag is None
    assert args.no_run_dir is False
    assert args.inference_server is None
    assert args.image_encoding == "jpeg"
    assert args.jpeg_quality == 95
    assert args.rpc_timeout_sec == 120.0
    assert args.rpc_connect_timeout_sec == 30.0


def test_remote_flags_parse_and_build_remote_adapter_without_connecting():
    parser = carlamayo.build_parser()
    args = parser.parse_args(
        ["--version", "1.5", "--loop", "closed", "--inference-server", "10.0.0.2:50051",
         "--image-encoding", "raw_rgb8", "--jpeg-quality", "80", "--rpc-timeout-sec", "5"]
    )
    adapter = carlamayo.build_adapter(args, parser)
    from module.remote.client import RemoteAlpamayoAdapter

    assert isinstance(adapter, RemoteAlpamayoAdapter)
    assert adapter.is_remote and adapter.target == "10.0.0.2:50051"
    assert adapter.expected_version == "1.5"
    assert adapter.image_encoding == "raw_rgb8" and adapter.jpeg_quality == 80
    assert adapter.rpc_timeout_sec == 5.0
    assert adapter.source_camera_configs == {}  # rig arrives with the handshake


@pytest.mark.parametrize(
    "extra",
    [["--quantization"], ["--oom-free"], ["--oom-free-resident", "4"], ["--device-map", "cuda:0"]],
)
def test_server_only_flags_are_rejected_with_remote(extra):
    parser = carlamayo.build_parser()
    args = parser.parse_args(["--version", "1.5", "--loop", "open", "--inference-server", "h:1", *extra])
    with pytest.raises(SystemExit):
        carlamayo.build_adapter(args, parser)


def test_main_with_remote_does_not_import_local_adapters(tmp_path, monkeypatch):
    import types

    seen = {}
    monkeypatch.setattr(carlamayo, "get_adapter", lambda v: (_ for _ in ()).throw(AssertionError("local adapter imported")))
    monkeypatch.setitem(
        __import__("sys").modules,
        "module.loops.open_loop",
        types.SimpleNamespace(run=lambda adapter, args: seen.update(adapter=adapter, run_dir=args.run_dir)),
    )
    carlamayo.main(
        ["--version", "1.5", "--loop", "open", "--inference-server", "h:1", "--runs-root", str(tmp_path)]
    )
    assert seen["adapter"].is_remote
    assert seen["adapter"].run_id == seen["run_dir"].run_id
    assert seen["run_dir"].run_id.endswith("_open_v1.5")


def test_main_creates_run_dir_and_passes_it_to_the_loop(tmp_path, monkeypatch):
    import types

    seen = {}

    def fake_run(adapter, args):
        seen["run_dir"] = args.run_dir
        seen["adapter"] = adapter
        print("inside loop")

    monkeypatch.setattr(carlamayo, "get_adapter", lambda v: types.SimpleNamespace(version="1.5"))
    monkeypatch.setitem(
        __import__("sys").modules, "module.loops.open_loop", types.SimpleNamespace(run=fake_run)
    )
    carlamayo.main(
        ["--version", "1.5", "--loop", "open", "--runs-root", str(tmp_path), "--run-tag", "t"]
    )
    run_dir = seen["run_dir"]
    assert run_dir.path_.parent == tmp_path
    assert run_dir.run_id.endswith("_open_v1.5_t")
    assert (run_dir.path_ / "args.json").exists()
    assert "inside loop" in (run_dir.path_ / "log.txt").read_text()


def test_main_no_run_dir_keeps_upstream_behaviour(monkeypatch):
    import types

    seen = {}
    monkeypatch.setattr(carlamayo, "get_adapter", lambda v: types.SimpleNamespace(version="2"))
    monkeypatch.setitem(
        __import__("sys").modules,
        "module.loops.closed_loop",
        types.SimpleNamespace(run=lambda a, args: seen.setdefault("run_dir", args.run_dir)),
    )
    carlamayo.main(["--version", "2", "--loop", "closed", "--no-run-dir"])
    assert seen["run_dir"] is None
