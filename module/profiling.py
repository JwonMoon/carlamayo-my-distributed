"""Lightweight run profiling: per-tick / per-request CSV rows plus system samples.

Everything is appended through a background thread so the CARLA tick loop and the
gRPC handlers never block on disk. Files land in ``runs/<run_id>/`` and are read
back by ``tools/analyze_run.py``.

Client side (sim host)                      Server side (inference host)
-----------------------                     ----------------------------
profile_client.csv      one row per tick    profile_server.csv      one row per request
profile_client_rpc.csv  one row per RPC     profile_server_sys.csv  one row per second
profile_client_sys.csv  one row per second
"""

from __future__ import annotations

import csv
import os
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

CLIENT_TICK_COLUMNS = [
    "frame", "sim_time", "wall_time", "tick_sec", "camera_capture_sec", "inference_sec",
    "control_sec", "ui_sec", "speed_kmh", "steer", "throttle", "brake",
    "trajectory_age_sec", "pending_inference", "has_trajectory",
]
CLIENT_RPC_COLUMNS = [
    "wall_time", "kind", "request_id", "frame_submitted", "encode_sec", "image_bytes",
    "request_bytes", "response_bytes", "rtt_sec", "server_total_sec", "inference_sec",
    "status", "error",
]
SERVER_REQUEST_COLUMNS = [
    "recv_wall_time", "kind", "request_id", "run_id", "frame", "request_bytes",
    "decode_sec", "prepare_sec", "inference_sec", "vlm_generate_sec", "total_sec",
    "gpu_mem_allocated_mb", "gpu_mem_peak_mb", "status", "error",
]
SYSTEM_COLUMNS = [
    "wall_time", "cpu_percent", "process_cpu_percent", "rss_mb", "ram_used_mb", "ram_total_mb",
    "gpu_util", "gpu_mem_used_mb", "gpu_mem_total_mb", "net_sent_bps", "net_recv_bps",
]

_SENTINEL = object()


class CsvRecorder:
    """Append dict rows to a CSV file from a background thread."""

    def __init__(self, path: str | os.PathLike, columns: list[str]):
        self.path = Path(path)
        self.columns = list(columns)
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._drain, name=f"csv:{self.path.name}", daemon=True)
        self._closed = False
        self.rows_written = 0
        self._thread.start()

    def put(self, row: dict[str, Any]) -> None:
        if not self._closed:
            self._queue.put(row)

    def _drain(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        with open(self.path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=self.columns, extrasaction="ignore")
            if new_file:
                writer.writeheader()
                fh.flush()
            while True:
                item = self._queue.get()
                if item is _SENTINEL:
                    break
                writer.writerow({k: _fmt(item.get(k, "")) for k in self.columns})
                self.rows_written += 1
                if self._queue.empty():
                    fh.flush()

    def close(self, timeout: float = 5.0) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put(_SENTINEL)
        self._thread.join(timeout=timeout)


def _fmt(value: Any) -> Any:
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, bool):
        return int(value)
    return value


# --------------------------------------------------------------------------- GPU
_nvml_lock = threading.Lock()
_nvml_handle = None
_nvml_failed = False


def gpu_stats(device_index: int = 0) -> dict[str, float]:
    """GPU utilisation and memory for the whole device (all processes), via NVML."""
    global _nvml_handle, _nvml_failed
    empty = {"gpu_util": "", "gpu_mem_used_mb": "", "gpu_mem_total_mb": ""}
    if _nvml_failed:
        return empty
    try:
        import pynvml
    except ImportError:
        _nvml_failed = True
        return empty
    with _nvml_lock:
        try:
            if _nvml_handle is None:
                pynvml.nvmlInit()
                _nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(device_index)
            util = pynvml.nvmlDeviceGetUtilizationRates(_nvml_handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(_nvml_handle)
        except Exception:  # noqa: BLE001 - no GPU / driver: profile without GPU columns
            _nvml_failed = True
            return empty
    return {
        "gpu_util": float(util.gpu),
        "gpu_mem_used_mb": mem.used / 1024**2,
        "gpu_mem_total_mb": mem.total / 1024**2,
    }


class SystemSampler:
    """Sample CPU / RAM / GPU / network every ``interval_sec`` into a recorder sink."""

    def __init__(self, sink: Callable[[], CsvRecorder | None], interval_sec: float = 1.0):
        self.sink = sink
        self.interval_sec = float(interval_sec)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="sys-sampler", daemon=True)
        self._last_net = None
        self._last_net_time = None

    def start(self) -> SystemSampler:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self.interval_sec + 1.0)

    def sample(self) -> dict[str, Any]:
        row: dict[str, Any] = {"wall_time": time.time()}
        try:
            import psutil

            proc = psutil.Process()
            vm = psutil.virtual_memory()
            row.update(
                cpu_percent=psutil.cpu_percent(interval=None),
                process_cpu_percent=proc.cpu_percent(interval=None),
                rss_mb=proc.memory_info().rss / 1024**2,
                ram_used_mb=vm.used / 1024**2,
                ram_total_mb=vm.total / 1024**2,
            )
            net = psutil.net_io_counters()
            now = time.monotonic()
            if self._last_net is not None:
                dt = max(now - self._last_net_time, 1e-6)
                row["net_sent_bps"] = (net.bytes_sent - self._last_net.bytes_sent) / dt
                row["net_recv_bps"] = (net.bytes_recv - self._last_net.bytes_recv) / dt
            self._last_net, self._last_net_time = net, now
        except ImportError:
            pass
        row.update(gpu_stats())
        return row

    def _run(self) -> None:
        self.sample()  # prime cpu_percent / net deltas
        while not self._stop.wait(self.interval_sec):
            recorder = self.sink()
            if recorder is not None:
                recorder.put(self.sample())


# ------------------------------------------------------------------ client side
class ClientProfiler:
    """Profiler for the CARLA-side loop; writes into the run folder."""

    def __init__(self, run_dir, interval_sec: float = 1.0, enabled: bool = True):
        self.enabled = bool(enabled) and run_dir is not None
        self.run_dir = run_dir
        self.tick_recorder = self.rpc_recorder = self.sys_recorder = None
        self._sampler = None
        if self.enabled:
            self.tick_recorder = CsvRecorder(run_dir.path("profile_client.csv"), CLIENT_TICK_COLUMNS)
            self.rpc_recorder = CsvRecorder(run_dir.path("profile_client_rpc.csv"), CLIENT_RPC_COLUMNS)
            self.sys_recorder = CsvRecorder(run_dir.path("profile_client_sys.csv"), SYSTEM_COLUMNS)
            self._sampler = SystemSampler(lambda: self.sys_recorder, interval_sec).start()

    def tick(self, **row: Any) -> None:
        if self.tick_recorder is not None:
            row.setdefault("wall_time", time.time())
            self.tick_recorder.put(row)

    def rpc(self, record: dict[str, Any]) -> None:
        """Sink for ``RemoteAlpamayoAdapter(on_rpc=...)`` and for local inference timings."""
        if self.rpc_recorder is not None:
            record = dict(record)
            record.setdefault("wall_time", time.time())
            self.rpc_recorder.put(record)

    def close(self) -> None:
        if self._sampler is not None:
            self._sampler.stop()
        for rec in (self.tick_recorder, self.rpc_recorder, self.sys_recorder):
            if rec is not None:
                rec.close()


# ------------------------------------------------------------------ server side
class ServerProfiler:
    """Per-run CSVs on the inference host, keyed by the ``run_id`` clients send."""

    def __init__(self, runs_root: str | os.PathLike, interval_sec: float = 1.0):
        self.runs_root = Path(runs_root)
        self.interval_sec = float(interval_sec)
        self._lock = threading.Lock()
        self._request_recorders: dict[str, CsvRecorder] = {}
        self._sys_recorders: dict[str, CsvRecorder] = {}
        self._active_run: str | None = None
        self._sampler = SystemSampler(self._active_sys_recorder, interval_sec).start()

    def _active_sys_recorder(self):
        with self._lock:
            return self._sys_recorders.get(self._active_run) if self._active_run else None

    def _recorders_for(self, run_id: str) -> CsvRecorder:
        safe = os.path.basename(run_id) or "no-run-id"
        with self._lock:
            if safe not in self._request_recorders:
                folder = self.runs_root / safe
                self._request_recorders[safe] = CsvRecorder(
                    folder / "profile_server.csv", SERVER_REQUEST_COLUMNS
                )
                self._sys_recorders[safe] = CsvRecorder(
                    folder / "profile_server_sys.csv", SYSTEM_COLUMNS
                )
            self._active_run = safe
            return self._request_recorders[safe]

    def on_request(self, record: dict[str, Any]) -> None:
        self._recorders_for(record.get("run_id") or "").put(record)

    def close(self) -> None:
        self._sampler.stop()
        with self._lock:
            for rec in list(self._request_recorders.values()) + list(self._sys_recorders.values()):
                rec.close()
