"""End-to-end smoke test of the CARLA loops against the fake gRPC server.

CARLA itself is replaced by an in-memory stand-in for ``CARLAInterface`` and the PID
follower, so the whole path exercised here is: launcher args -> run folder ->
RemoteAlpamayoAdapter handshake -> tick loop -> JPEG encode -> Predict RPC ->
trajectory selection -> control -> profiling CSVs. It runs in CI without a GPU.
"""

from __future__ import annotations

import csv
import sys
import time
import types

import numpy as np
import pytest

import carlamayo
from module import config as cfg
from module.remote import server as srv
from module.remote.fake_adapter import FakeAdapter
from module.run_dir import RunDir

SMALL_H, SMALL_W = 32, 48


class _StopLoop(KeyboardInterrupt):
    """Raised by the fake simulator to end the endless loop after N ticks."""


class FakeCarla:
    """Minimal stand-in for module.carla_interface.CARLAInterface."""

    instances: list[FakeCarla] = []

    def __init__(self, camera_configs=None, max_ticks=12, tick_sleep=0.0):
        self.tick_sleep = tick_sleep
        self.camera_configs = dict(camera_configs or {})
        self.camera_order = list(self.camera_configs)
        self.max_ticks = max_ticks
        self.ticks = 0
        self.controls = []
        self.autopilot = None
        self.tm_port = 8000
        self.world = object()
        self.ego_vehicle = types.SimpleNamespace(get_transform=lambda: "tf")
        self.history = []
        FakeCarla.instances.append(self)

    # lifecycle ---------------------------------------------------------------
    def connect(self, host="localhost", port=2000):
        self.connected = (host, port)

    def load_map(self, name):
        self.map = name

    def spawn_ego_vehicle(self):
        return self.ego_vehicle

    def enable_synchronous_mode(self):
        pass

    def spawn_npcs(self, num_vehicles=0, num_walkers=0):
        pass

    def setup_cameras(self):
        pass

    def setup_collision_sensor(self):
        pass

    def set_ego_autopilot(self, enabled, target_speed_kmh=None):
        self.autopilot = enabled

    def cleanup(self):
        self.cleaned = True

    # per tick ----------------------------------------------------------------
    def tick(self):
        self.ticks += 1
        if self.ticks > self.max_ticks:
            raise _StopLoop()
        if self.tick_sleep:
            time.sleep(self.tick_sleep)  # let the async worker deliver results

    def get_ego_state(self):
        return {"x": float(self.ticks), "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
                "speed": 3.0}

    def update_history(self, state):
        self.history.append(state)

    def get_history_in_local_frame(self):
        return (np.zeros((cfg.NUM_HISTORY, 3), dtype=np.float32),
                np.tile(np.eye(3, dtype=np.float32), (cfg.NUM_HISTORY, 1, 1)))

    def get_collision_count(self):
        return 0

    def get_last_collision_event(self):
        return None

    def reset_collision_history(self):
        pass

    def get_camera_images(self):
        n = len(self.camera_order)
        return np.full((n, cfg.IMG_HEIGHT, cfg.IMG_WIDTH, 3), 10 + self.ticks, dtype=np.uint8)

    def apply_control(self, steering, throttle, brake):
        self.controls.append((float(steering), float(throttle), float(brake)))

    def get_ego_control(self):
        return {"steer": 0.05, "throttle": 0.4, "brake": 0.0}

    def respawn_ego_vehicle(self):
        pass


class FakePID:
    def __init__(self, world, vehicle):
        pass

    def compute_control(self, vehicle_tf, wp_ego, speed_mps):
        assert wp_ego.shape == (64, 3)
        return 0.1, 0.5, 0.0, {"mode": "fake"}


class NoVideo:
    def __init__(self, *a, **k):
        self.frames = 0

    def add_frame(self, frame):
        self.frames += 1

    def save(self):
        pass


@pytest.fixture
def fake_carla_modules(monkeypatch):
    """Make ``import carla`` succeed so the loop modules import without the wheel."""
    fake = types.ModuleType("carla")
    for name in ("Location", "Transform", "Rotation", "VehicleControl", "Vector3D", "Client"):
        setattr(fake, name, type(name, (), {"__init__": lambda self, *a, **k: None}))
    fake.command = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "carla", fake)
    monkeypatch.setattr(cfg, "IMG_HEIGHT", SMALL_H)
    monkeypatch.setattr(cfg, "IMG_WIDTH", SMALL_W)
    monkeypatch.setattr(cfg, "NPC_VEHICLE_COUNT", 0)
    monkeypatch.setattr(cfg, "NPC_WALKER_COUNT", 0)
    FakeCarla.instances.clear()
    yield


@pytest.fixture
def fake_server(tmp_path):
    adapter = FakeAdapter(version="1.5")  # the launcher only accepts real version tokens
    model, processor = adapter.load_model()
    servicer = srv.AlpamayoServicer(adapter, model, processor, runs_root=tmp_path / "server_runs")
    server, port = srv.create_server(servicer, host="127.0.0.1", port=0)
    server.start()
    yield servicer, f"127.0.0.1:{port}"
    server.stop(grace=None)


def _args(loop, target, tmp_path, *extra):
    parser = carlamayo.build_parser()
    args = parser.parse_args(
        ["--version", "1.5", "--loop", loop, "--inference-server", target,
         "--runs-root", str(tmp_path / "runs"), "--profile-interval-sec", "0.05", *extra]
    )
    args.run_dir = RunDir.create(loop, "1.5", args.mode if loop == "closed" else None, root=args.runs_root)
    return args


def _patch_loop(monkeypatch, module, max_ticks, tick_sleep=0.0):
    monkeypatch.setattr(
        module, "CARLAInterface", lambda camera_configs=None: FakeCarla(camera_configs, max_ticks, tick_sleep)
    )
    monkeypatch.setattr(module, "VideoRecorder", NoVideo)
    if hasattr(module, "OfficialPIDFollower"):
        monkeypatch.setattr(module, "OfficialPIDFollower", FakePID)


def _csv_rows(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.mark.parametrize("async_flag", [[], ["--async"]], ids=["sync", "async"])
def test_closed_loop_drives_with_remote_inference(fake_carla_modules, fake_server, tmp_path, monkeypatch, async_flag):
    from module.loops import closed_loop

    servicer, target = fake_server
    _patch_loop(monkeypatch, closed_loop, max_ticks=14, tick_sleep=0.05 if async_flag else 0.0)
    args = _args("closed", target, tmp_path, *async_flag)
    adapter = carlamayo.build_adapter(args)

    closed_loop.run(adapter, args)
    args.run_dir.close()

    sim = FakeCarla.instances[-1]
    assert sim.cleaned and sim.map == cfg.CARLA_MAP
    assert sim.camera_order == list(FakeAdapter.source_camera_configs)  # rig came from the server
    assert servicer.requests_served >= 1
    # After the first prediction the PID output (0.5 throttle, smoothed) is applied.
    assert any(throttle > 0 for _, throttle, _ in sim.controls)
    # First ticks (buffer not full) brake.
    assert sim.controls[0] == (0.0, 0.0, 1.0)

    run = args.run_dir.path_
    ticks = _csv_rows(run / "profile_client.csv")
    assert len(ticks) == 14 and ticks[-1]["has_trajectory"] == "1"
    rpcs = _csv_rows(run / "profile_client_rpc.csv")
    assert rpcs and all(r["status"] == "OK" for r in rpcs)
    assert all(int(r["request_bytes"]) > 0 for r in rpcs)
    assert (run / "profile_client_sys.csv").exists()
    # The server mirrored the client's run folder by run_id.
    assert (tmp_path / "server_runs" / args.run_dir.run_id / "server_info.json").exists()


def test_closed_loop_brakes_on_stale_trajectory(fake_carla_modules, fake_server, tmp_path, monkeypatch):
    from module.loops import _common, closed_loop

    _, target = fake_server
    _patch_loop(monkeypatch, closed_loop, max_ticks=8)
    # Every trajectory is immediately "too old": the guard must drop it and brake.
    monkeypatch.setattr(closed_loop, "trajectory_is_stale", lambda ts, max_age_sec=None: ts is not None)
    args = _args("closed", target, tmp_path, "--trajectory-max-age-sec", "0.001")
    closed_loop.run(carlamayo.build_adapter(args), args)
    args.run_dir.close()
    sim = FakeCarla.instances[-1]
    assert all(brake == 1.0 for _, _, brake in sim.controls)
    assert _common.trajectory_max_age_sec(args) == 0.001


def test_live_open_loop_observes_with_remote_inference(fake_carla_modules, fake_server, tmp_path, monkeypatch):
    from module.loops import live_open_loop

    servicer, target = fake_server
    _patch_loop(monkeypatch, live_open_loop, max_ticks=10, tick_sleep=0.05)
    args = _args("live-open", target, tmp_path, "--async")
    live_open_loop.run(carlamayo.build_adapter(args), args)
    args.run_dir.close()

    sim = FakeCarla.instances[-1]
    assert sim.autopilot is False  # switched on for the run, off again at cleanup
    assert sim.controls == []  # the model never touches the wheel
    assert servicer.requests_served >= 1
    ticks = _csv_rows(args.run_dir.path_ / "profile_client.csv")
    assert len(ticks) == 10 and ticks[0]["throttle"] == "0.4"
