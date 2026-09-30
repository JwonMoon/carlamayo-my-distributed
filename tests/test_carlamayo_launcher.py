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
