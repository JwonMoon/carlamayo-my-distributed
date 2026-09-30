"""``RemoteAlpamayoAdapter``: the ``AlpamayoAdapter`` interface backed by gRPC.

The loops keep calling ``prepare_model_input`` / ``run_inference`` / ``run_vqa`` as
they do for a local model; this adapter encodes the arrays, sends them to
``alpamayo_server.py`` on the inference host and decodes the reply. It imports
neither torch nor any model package, so it runs on the CARLA sim host.

Life cycle
----------
``load_model()`` opens the channel and performs the ``GetModelInfo`` handshake: the
served version must match ``--version`` and the server's frame / history / image
size constants must match this host's ``module/config.py``; the camera rig and the
capability flags are then copied from the server. After a connection error the
next call repeats the handshake, so a server restarted with a different
``--version`` is caught instead of silently changing the camera rig.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

import grpc
import numpy as np

from module import config as cfg
from module.adapters import normalize_version
from module.adapters.base import AlpamayoAdapter
from module.remote import alpamayo_inference_pb2 as pb
from module.remote import alpamayo_inference_pb2_grpc as pb_grpc
from module.remote import codec
from module.remote.server import PROTOCOL_VERSION, grpc_channel_options

DEFAULT_RPC_TIMEOUT_SEC = 120.0
DEFAULT_CONNECT_TIMEOUT_SEC = 30.0
WARMUP_POLL_SEC = 2.0


class RemoteInferenceError(RuntimeError):
    """A remote call failed. ``code`` is the gRPC status code name (or a local reason)."""

    def __init__(self, code: str, details: str):
        super().__init__(f"{code}: {details}")
        self.code = code
        self.details = details


class RemoteAlpamayoAdapter(AlpamayoAdapter):
    is_remote = True

    def __init__(
        self,
        target: str,
        expected_version: str | None = None,
        *,
        image_encoding: str = codec.ENCODING_JPEG,
        jpeg_quality: int = codec.DEFAULT_JPEG_QUALITY,
        rpc_timeout_sec: float = DEFAULT_RPC_TIMEOUT_SEC,
        connect_timeout_sec: float = DEFAULT_CONNECT_TIMEOUT_SEC,
        run_id: str = "",
        max_message_mb: int = 512,
        on_rpc: Callable[[dict[str, Any]], None] | None = None,
    ):
        if image_encoding not in codec.IMAGE_ENCODINGS:
            raise ValueError(f"image_encoding must be one of {codec.IMAGE_ENCODINGS}")
        self.target = target
        self.expected_version = normalize_version(expected_version) if expected_version else None
        self.image_encoding = image_encoding
        self.jpeg_quality = int(jpeg_quality)
        self.rpc_timeout_sec = float(rpc_timeout_sec)
        self.connect_timeout_sec = float(connect_timeout_sec)
        self.run_id = run_id
        self.max_message_mb = max_message_mb
        self.on_rpc = on_rpc

        self.version = expected_version or ""
        self.model_id = ""
        self.display_name = f"remote Alpamayo @ {target}"
        self.source_camera_configs = {}
        self.source_camera_indices = ()
        self.viz_camera_slot = 0
        self.device_map = ""
        self.server_git_sha = ""
        self.vram_allocated_gb = 0.0
        self.model_info: pb.ModelInfo | None = None

        self._channel: grpc.Channel | None = None
        self._stub: pb_grpc.AlpamayoInferenceStub | None = None
        self._needs_handshake = True
        self._request_counter = 0

    # ---------------------------------------------------------------- lifecycle
    def load_model(self, use_quantization=False, device_map="auto", oom_free=False, oom_kwargs=None):
        """Connect and handshake. Model options are server-side; they are ignored here."""
        self.connect()
        return None, None

    def connect(self) -> pb.ModelInfo:
        if self._channel is None:
            self._channel = grpc.insecure_channel(
                self.target, options=grpc_channel_options(self.max_message_mb)
            )
            self._stub = pb_grpc.AlpamayoInferenceStub(self._channel)
        try:
            grpc.channel_ready_future(self._channel).result(timeout=self.connect_timeout_sec)
        except grpc.FutureTimeoutError as exc:
            raise RemoteInferenceError(
                "UNAVAILABLE", f"no inference server at {self.target} after {self.connect_timeout_sec:.0f}s"
            ) from exc
        return self._handshake()

    def close(self) -> None:
        if self._channel is not None:
            self._channel.close()
            self._channel = None
            self._stub = None
            self._needs_handshake = True

    def _handshake(self) -> pb.ModelInfo:
        deadline = time.monotonic() + self.connect_timeout_sec
        while True:
            try:
                info = self._stub.GetModelInfo(
                    pb.GetModelInfoRequest(client_protocol_version=PROTOCOL_VERSION),
                    timeout=self.connect_timeout_sec,
                )
            except grpc.RpcError as exc:
                raise RemoteInferenceError(exc.code().name, exc.details()) from exc
            if info.warmed_up or time.monotonic() >= deadline:
                break
            print(f"[remote] server at {self.target} is still loading; waiting...")
            time.sleep(min(WARMUP_POLL_SEC, max(0.0, deadline - time.monotonic())))
        self._validate(info)
        self._apply(info)
        self._needs_handshake = False
        return info

    def _validate(self, info: pb.ModelInfo) -> None:
        problems = []
        if info.protocol_version != PROTOCOL_VERSION:
            problems.append(f"protocol {info.protocol_version!r} != {PROTOCOL_VERSION!r}")
        if self.expected_version and normalize_version(info.version) != self.expected_version:
            problems.append(
                f"server serves Alpamayo {info.version!r} but --version {self.expected_version!r} was requested"
            )
        if not info.warmed_up:
            problems.append("server is not warmed up")
        for name, mine, theirs in (
            ("NUM_FRAMES", cfg.NUM_FRAMES, info.num_frames),
            ("NUM_HISTORY", cfg.NUM_HISTORY, info.num_history),
            ("IMG_HEIGHT", cfg.IMG_HEIGHT, info.img_height),
            ("IMG_WIDTH", cfg.IMG_WIDTH, info.img_width),
            ("NUM_TRAJ_SAMPLES", cfg.NUM_TRAJ_SAMPLES, info.num_traj_samples),
        ):
            if int(mine) != int(theirs):
                problems.append(f"{name}: client {mine} != server {theirs}")
        if info.image_encodings and self.image_encoding not in info.image_encodings:
            problems.append(f"server does not accept image encoding {self.image_encoding!r}")
        if problems:
            raise RemoteInferenceError("FAILED_PRECONDITION", "; ".join(problems))

    def _apply(self, info: pb.ModelInfo) -> None:
        self.model_info = info
        self.version = info.version
        self.model_id = info.model_id
        self.display_name = f"{info.display_name} (remote @ {self.target})"
        self.source_camera_configs = {
            cam.name: {"x": cam.x, "y": cam.y, "z": cam.z, "pitch": cam.pitch, "yaw": cam.yaw, "fov": cam.fov}
            for cam in info.cameras
        }
        self.source_camera_indices = tuple(info.camera_indices)
        self.viz_camera_slot = int(info.viz_camera_slot)
        self.supports_navigation = bool(info.supports_navigation)
        self.supports_vqa = bool(info.supports_vqa)
        self.supports_oom_free = bool(info.supports_oom_free)
        self.quantization = bool(info.quantization)
        self.oom_free = bool(info.oom_free)
        self.device_map = info.device_map
        self.server_git_sha = info.server_git_sha
        self.vram_allocated_gb = float(info.vram_allocated_gb)

    def runtime_summary(self) -> str:
        return (
            f"Remote inference: {self.display_name}, server VRAM {self.vram_allocated_gb:.1f} GB, "
            f"quantization={'ON' if self.quantization else 'OFF'}, "
            f"oom_free={'ON' if self.oom_free else 'OFF'}, "
            f"images={self.image_encoding}"
            + (f" q{self.jpeg_quality}" if self.image_encoding == codec.ENCODING_JPEG else "")
        )

    # ------------------------------------------------------------- inference
    def prepare_model_input(self, images_array, history_xyz, history_rot, t0_us):
        """Encode once here (this runs in the async worker thread), send in run_*."""
        images = np.asarray(images_array)
        if not self.source_camera_configs:
            raise RemoteInferenceError("FAILED_PRECONDITION", "load_model() has not run yet")
        if images.ndim != 5 or images.shape[0] != self.num_cameras:
            raise ValueError(
                f"{self.display_name} expects ({self.num_cameras}, T, H, W, 3) images, got {images.shape}"
            )
        t0 = time.perf_counter()
        stack = codec.encode_image_stack(images, self.image_encoding, self.jpeg_quality)
        return {
            "images": stack,
            "history_xyz": codec.array_to_tensor(np.asarray(history_xyz, dtype=np.float32)),
            "history_rot": codec.array_to_tensor(np.asarray(history_rot, dtype=np.float32)),
            "t0_us": int(t0_us),
            "encode_sec": time.perf_counter() - t0,
            "image_bytes": codec.stack_num_bytes(stack),
            "meta": {},
        }

    def _meta(self, data: dict[str, Any]) -> pb.ClientMeta:
        self._request_counter += 1
        meta = data.get("meta") or {}
        return pb.ClientMeta(
            request_id=meta.get("request_id") or f"{self._request_counter:06d}-{uuid.uuid4().hex[:8]}",
            frame=int(meta.get("frame", 0)),
            prompt_revision=int(meta.get("prompt_revision", 0)),
            respawn_revision=int(meta.get("respawn_revision", 0)),
            run_id=self.run_id,
        )

    def run_inference(
        self, model, processor, data,
        navigation_text=None, navigation_weight=1.0, vlm_generate_timing=None, seed=None,
    ):
        request = pb.PredictRequest(
            meta=self._meta(data),
            images=data["images"],
            history_xyz=data["history_xyz"],
            history_rot=data["history_rot"],
            t0_us=data["t0_us"],
            navigation_text=navigation_text or "",
            navigation_weight=float(navigation_weight),
        )
        if seed is not None:
            request.seed = int(seed)
        response, record = self._call("predict", lambda: self._stub.Predict(request, timeout=self.rpc_timeout_sec), request, data)
        if vlm_generate_timing is not None and response.timings.vlm_generate_last_sec:
            vlm_generate_timing.record(response.timings.vlm_generate_last_sec)
        pred_xyz = codec.tensor_to_array(response.pred_xyz)
        extra = {"cot": response.cot_text, "timings": _timings_dict(response.timings), **record}
        return pred_xyz, extra

    def run_vqa(self, model, processor, data, question, seed=None):
        request = pb.VqaRequest(
            meta=self._meta(data),
            images=data["images"],
            history_xyz=data["history_xyz"],
            history_rot=data["history_rot"],
            t0_us=data["t0_us"],
            question=question,
        )
        if seed is not None:
            request.seed = int(seed)
        response, record = self._call("vqa", lambda: self._stub.AnswerQuestion(request, timeout=self.rpc_timeout_sec), request, data)
        return {
            "answer": response.answer,
            "raw_answer": response.raw_answer,
            "timings": _timings_dict(response.timings),
            **record,
        }

    def _call(self, kind: str, fn, request, data: dict[str, Any]):
        if self._stub is None:
            self.connect()
        elif self._needs_handshake:
            self._handshake()
        record: dict[str, Any] = {
            "kind": kind,
            "request_id": request.meta.request_id,
            "frame_submitted": int(request.meta.frame),
            "encode_sec": float(data.get("encode_sec", 0.0)),
            "image_bytes": int(data.get("image_bytes", 0)),
            "request_bytes": request.ByteSize(),
            "response_bytes": 0,
            "rtt_sec": 0.0,
            "server_total_sec": 0.0,
            "inference_sec": 0.0,
            "status": "OK",
        }
        t0 = time.perf_counter()
        try:
            response = fn()
        except grpc.RpcError as exc:
            record.update(rtt_sec=time.perf_counter() - t0, status=exc.code().name, error=exc.details())
            self._notify(record)
            if exc.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.FAILED_PRECONDITION):
                self._needs_handshake = True
            raise RemoteInferenceError(exc.code().name, exc.details()) from exc
        record.update(
            rtt_sec=time.perf_counter() - t0,
            response_bytes=response.ByteSize(),
            server_total_sec=float(response.timings.total_sec),
            inference_sec=float(response.timings.inference_sec),
        )
        self._notify(record)
        return response, record

    def _notify(self, record: dict[str, Any]) -> None:
        if self.on_rpc is None:
            return
        try:
            self.on_rpc(dict(record))
        except Exception as exc:  # noqa: BLE001 - profiling must never break driving
            print(f"[remote] on_rpc hook failed: {exc}")

    # ---------------------------------------------------------------- outputs
    def extract_cot_text(self, extra):
        return str(extra.get("cot", "")) if isinstance(extra, dict) else ""

    def extract_answer_text(self, extra):
        return str(extra.get("answer", "")) if isinstance(extra, dict) else ""


def _timings_dict(t: pb.Timings) -> dict[str, float]:
    return {
        "decode_sec": t.decode_sec,
        "prepare_sec": t.prepare_sec,
        "inference_sec": t.inference_sec,
        "total_sec": t.total_sec,
        "vlm_generate_calls": t.vlm_generate_calls,
        "vlm_generate_last_sec": t.vlm_generate_last_sec,
        "gpu_mem_allocated_gb": t.gpu_mem_allocated_gb,
        "gpu_mem_peak_gb": t.gpu_mem_peak_gb,
    }
