"""gRPC servicer that exposes one Alpamayo adapter to remote CARLA clients.

The servicer wraps an already-loaded ``(adapter, model, processor)`` triple. It
decodes the image stack sent by the client back into the ``(cam, frame, H, W, 3)``
uint8 array the adapter expects, so ``adapter.prepare_model_input`` /
``run_inference`` / ``run_vqa`` run exactly as they do in the single-host setup.

Only one model call runs at a time (``threading.Lock``); a second concurrent request
is refused with ``RESOURCE_EXHAUSTED`` rather than queued, because the client never
has more than one request in flight and a queue would only hide a misconfiguration.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Callable
from concurrent import futures
from pathlib import Path
from typing import Any

import grpc
import numpy as np

from module import config as cfg
from module.adapters._text import extract_text_field
from module.inference import configure_cuda_linalg_library
from module.remote import alpamayo_inference_pb2 as pb
from module.remote import alpamayo_inference_pb2_grpc as pb_grpc
from module.remote import codec
from module.run_dir import git_sha
from module.vlm_generate_optimization import VlmGenerateTiming

PROTOCOL_VERSION = "1"
DEFAULT_PORT = 50051
DEFAULT_MAX_MESSAGE_MB = 512
CUSOLVER_ERROR = "CUSOLVER_STATUS_INTERNAL_ERROR"


def grpc_channel_options(max_message_mb: int = DEFAULT_MAX_MESSAGE_MB) -> list[tuple[str, int]]:
    """Options shared by server and client: big messages, keepalive."""
    max_bytes = int(max_message_mb) * 1024 * 1024
    return [
        ("grpc.max_send_message_length", max_bytes),
        ("grpc.max_receive_message_length", max_bytes),
        ("grpc.keepalive_time_ms", 20_000),
        ("grpc.keepalive_timeout_ms", 10_000),
        ("grpc.http2.max_pings_without_data", 0),
        ("grpc.keepalive_permit_without_calls", 1),
    ]


def _gpu_memory_gb() -> tuple[float, float]:
    """(allocated, peak) GB on the current CUDA device, or zeros without torch/CUDA."""
    try:
        import torch
    except ImportError:
        return 0.0, 0.0
    if not torch.cuda.is_available():
        return 0.0, 0.0
    return (
        torch.cuda.memory_allocated() / 1024**3,
        torch.cuda.max_memory_allocated() / 1024**3,
    )


def _reset_gpu_peak() -> None:
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()


def build_model_info(
    adapter: Any,
    *,
    warmed_up: bool,
    device_map: str = "auto",
) -> pb.ModelInfo:
    info = pb.ModelInfo(
        protocol_version=PROTOCOL_VERSION,
        version=str(adapter.version),
        model_id=str(adapter.model_id),
        display_name=str(adapter.display_name),
        camera_indices=list(adapter.source_camera_indices),
        viz_camera_slot=int(adapter.viz_camera_slot),
        supports_navigation=bool(adapter.supports_navigation),
        supports_vqa=bool(adapter.supports_vqa),
        supports_oom_free=bool(adapter.supports_oom_free),
        quantization=bool(getattr(adapter, "quantization", False)),
        oom_free=bool(getattr(adapter, "oom_free", False)),
        device_map=str(device_map),
        num_frames=int(cfg.NUM_FRAMES),
        num_history=int(cfg.NUM_HISTORY),
        img_height=int(cfg.IMG_HEIGHT),
        img_width=int(cfg.IMG_WIDTH),
        num_traj_samples=int(cfg.NUM_TRAJ_SAMPLES),
        warmed_up=bool(warmed_up),
        vram_allocated_gb=_gpu_memory_gb()[0],
        server_git_sha=git_sha(),
        image_encodings=list(codec.IMAGE_ENCODINGS),
    )
    for name, cam in adapter.source_camera_configs.items():
        info.cameras.append(
            pb.CameraConfig(
                name=name, x=cam["x"], y=cam["y"], z=cam["z"],
                pitch=cam["pitch"], yaw=cam["yaw"], fov=cam["fov"],
            )
        )
    return info


class _RequestError(Exception):
    """Raised inside a handler to abort with a specific status code."""

    def __init__(self, code: grpc.StatusCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _to_numpy(pred_xyz) -> np.ndarray:
    if hasattr(pred_xyz, "detach"):
        return pred_xyz.detach().cpu().numpy().astype(np.float32, copy=False)
    return np.asarray(pred_xyz, dtype=np.float32)


class AlpamayoServicer(pb_grpc.AlpamayoInferenceServicer):
    """Serve ``adapter`` over gRPC. ``on_request`` receives one dict per handled call."""

    def __init__(
        self,
        adapter: Any,
        model: Any = None,
        processor: Any = None,
        *,
        warmed_up: bool = True,
        device_map: str = "auto",
        runs_root: str | os.PathLike | None = None,
        on_request: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.adapter = adapter
        self.model = model
        self.processor = processor
        self.warmed_up = warmed_up
        self.device_map = device_map
        self.runs_root = Path(runs_root) if runs_root else None
        self.on_request = on_request
        self.vlm_generate_timing = VlmGenerateTiming()
        self._model_lock = threading.Lock()
        self._known_runs: set[str] = set()
        self.requests_served = 0

    # ------------------------------------------------------------------ RPCs
    def GetModelInfo(self, request, context):
        if request.client_protocol_version and request.client_protocol_version != PROTOCOL_VERSION:
            context.abort(
                grpc.StatusCode.FAILED_PRECONDITION,
                f"client protocol {request.client_protocol_version!r} != server {PROTOCOL_VERSION!r}",
            )
        return build_model_info(self.adapter, warmed_up=self.warmed_up, device_map=self.device_map)

    def Predict(self, request, context):
        return self._handle(request, context, kind="predict")

    def AnswerQuestion(self, request, context):
        return self._handle(request, context, kind="vqa")

    # -------------------------------------------------------------- internals
    def _handle(self, request, context, *, kind: str):
        if not self.warmed_up:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, "model is still loading / warming up")
        if not self._model_lock.acquire(blocking=False):
            context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "another inference is in progress")
        t_start = time.perf_counter()
        meta = request.meta
        request_id = meta.request_id or uuid.uuid4().hex
        record: dict[str, Any] = {
            "kind": kind,
            "request_id": request_id,
            "run_id": meta.run_id,
            "frame": int(meta.frame),
            "recv_wall_time": time.time(),
            "request_bytes": request.ByteSize(),
        }
        try:
            self._register_run(meta.run_id)
            try:
                images = codec.decode_image_stack(request.images)
                history_xyz = codec.tensor_to_array(request.history_xyz)
                history_rot = codec.tensor_to_array(request.history_rot)
            except ValueError as exc:
                raise _RequestError(
                    grpc.StatusCode.INVALID_ARGUMENT, f"bad request payload: {exc}"
                ) from exc
            t_decoded = time.perf_counter()

            _reset_gpu_peak()
            model_data = self.adapter.prepare_model_input(
                images, history_xyz, history_rot, int(request.t0_us)
            )
            t_prepared = time.perf_counter()

            seed = request.seed if request.HasField("seed") else None
            if kind == "predict":
                pred_xyz, extra = self._run_with_linalg_fallback(
                    lambda: self.adapter.run_inference(
                        self.model, self.processor, model_data,
                        navigation_text=request.navigation_text or None,
                        navigation_weight=float(request.navigation_weight or 1.0),
                        vlm_generate_timing=self.vlm_generate_timing,
                        seed=seed,
                    )
                )
            else:
                extra = self._run_with_linalg_fallback(
                    lambda: self.adapter.run_vqa(
                        self.model, self.processor, model_data,
                        question=request.question, seed=seed,
                    )
                )
                pred_xyz = None
            t_done = time.perf_counter()

            allocated_gb, peak_gb = _gpu_memory_gb()
            timings = pb.Timings(
                decode_sec=t_decoded - t_start,
                prepare_sec=t_prepared - t_decoded,
                inference_sec=t_done - t_prepared,
                total_sec=t_done - t_start,
                vlm_generate_calls=int(self.vlm_generate_timing.calls),
                vlm_generate_last_sec=float(self.vlm_generate_timing.last_time_sec),
                gpu_mem_allocated_gb=allocated_gb,
                gpu_mem_peak_gb=peak_gb,
            )
            echo = pb.ClientMeta(
                request_id=request_id, frame=meta.frame,
                prompt_revision=meta.prompt_revision, respawn_revision=meta.respawn_revision,
                run_id=meta.run_id,
            )
            if kind == "predict":
                response = pb.PredictResponse(
                    meta=echo,
                    pred_xyz=codec.array_to_tensor(_to_numpy(pred_xyz)),
                    cot_text=self.adapter.extract_cot_text(extra) or "",
                    timings=timings,
                )
            else:
                response = pb.VqaResponse(
                    meta=echo,
                    answer=self.adapter.extract_answer_text(extra) or "",
                    raw_answer=extract_text_field(extra, "raw_answer") or "",
                    timings=timings,
                )
            record.update(
                decode_sec=timings.decode_sec, prepare_sec=timings.prepare_sec,
                inference_sec=timings.inference_sec, total_sec=timings.total_sec,
                vlm_generate_sec=timings.vlm_generate_last_sec,
                gpu_mem_allocated_mb=allocated_gb * 1024, gpu_mem_peak_mb=peak_gb * 1024,
                status="OK",
            )
            self.requests_served += 1
            return response
        except _RequestError as exc:
            record.update(status=exc.code.name, error=exc.message, total_sec=time.perf_counter() - t_start)
            context.abort(exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001 - surfaced to the client as INTERNAL
            record.update(status="INTERNAL", error=str(exc), total_sec=time.perf_counter() - t_start)
            context.abort(grpc.StatusCode.INTERNAL, f"{type(exc).__name__}: {exc}")
        finally:
            self._model_lock.release()
            if self.on_request is not None:
                try:
                    self.on_request(record)
                except Exception as exc:  # noqa: BLE001 - never let logging break serving
                    print(f"[server] on_request hook failed: {exc}")

    @staticmethod
    def _run_with_linalg_fallback(fn):
        """Retry once on the cuSOLVER failure some GPUs hit, switching linalg to MAGMA."""
        try:
            return fn()
        except RuntimeError as exc:
            if CUSOLVER_ERROR not in str(exc):
                raise
            print("[server] cuSOLVER linalg backend failed; switching to MAGMA and retrying once.")
            configure_cuda_linalg_library("magma")
            return fn()

    def _register_run(self, run_id: str) -> None:
        """Mirror the client's run folder on this host the first time a run_id is seen."""
        if not run_id or self.runs_root is None or run_id in self._known_runs:
            return
        safe = os.path.basename(run_id)
        if safe != run_id:
            return  # never let a client pick a path outside runs_root
        run_path = self.runs_root / safe
        run_path.mkdir(parents=True, exist_ok=True)
        info = {
            "run_id": run_id,
            "first_request_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "server_git_sha": git_sha(),
            "version": str(self.adapter.version),
            "model_id": str(self.adapter.model_id),
            "quantization": bool(getattr(self.adapter, "quantization", False)),
            "oom_free": bool(getattr(self.adapter, "oom_free", False)),
            "device_map": self.device_map,
        }
        (run_path / "server_info.json").write_text(json.dumps(info, indent=2))
        self._known_runs.add(run_id)
        print(f"[server] run folder: {run_path}")


def create_server(
    servicer: AlpamayoServicer,
    host: str = "0.0.0.0",
    port: int = DEFAULT_PORT,
    *,
    max_message_mb: int = DEFAULT_MAX_MESSAGE_MB,
    max_workers: int = 4,
) -> tuple[grpc.Server, int]:
    """Build (not start) a gRPC server with health checking. Returns (server, bound port)."""
    from grpc_health.v1 import health, health_pb2, health_pb2_grpc

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        options=grpc_channel_options(max_message_mb),
    )
    pb_grpc.add_AlpamayoInferenceServicer_to_server(servicer, server)
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    status = (
        health_pb2.HealthCheckResponse.SERVING
        if servicer.warmed_up
        else health_pb2.HealthCheckResponse.NOT_SERVING
    )
    health_servicer.set("", status)
    health_servicer.set("carlamayo.v1.AlpamayoInference", status)
    servicer.health_servicer = health_servicer
    bound_port = server.add_insecure_port(f"{host}:{port}")
    if bound_port == 0:
        raise RuntimeError(f"could not bind gRPC server to {host}:{port}")
    return server, bound_port


def set_serving(servicer: AlpamayoServicer, serving: bool) -> None:
    from grpc_health.v1 import health_pb2

    servicer.warmed_up = serving
    health = getattr(servicer, "health_servicer", None)
    if health is not None:
        status = (
            health_pb2.HealthCheckResponse.SERVING
            if serving
            else health_pb2.HealthCheckResponse.NOT_SERVING
        )
        health.set("", status)
        health.set("carlamayo.v1.AlpamayoInference", status)
