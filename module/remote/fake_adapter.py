"""A torch-free stand-in for an Alpamayo adapter, for tests and dry runs.

It advertises the four-camera rig and returns a trajectory that is a deterministic
function of its inputs, so client/server round-trip tests can check that nothing was
lost or reordered on the wire.
"""

from __future__ import annotations

import time

import numpy as np

from module import config as cfg
from module.adapters._rigs import FOUR_CAMERA_INDICES, FOUR_CAMERA_RIG, FRONT_WIDE_SLOT
from module.adapters.base import AlpamayoAdapter

HORIZON = 64


class FakeAdapter(AlpamayoAdapter):
    version = "fake"
    model_id = "carlamayo/fake"
    display_name = "Fake Alpamayo"

    source_camera_configs = FOUR_CAMERA_RIG
    source_camera_indices = FOUR_CAMERA_INDICES
    viz_camera_slot = FRONT_WIDE_SLOT

    supports_navigation = True
    supports_vqa = True
    supports_oom_free = False

    def __init__(self, sleep_sec: float = 0.0, fail_with: Exception | None = None, version="fake"):
        self.sleep_sec = sleep_sec
        self.fail_with = fail_with
        self.version = version
        self.calls = []

    def load_model(self, use_quantization=False, device_map="auto", oom_free=False, oom_kwargs=None):
        self.quantization = bool(use_quantization)
        self.oom_free = bool(oom_free)
        return object(), object()

    def runtime_summary(self) -> str:
        return "Fake model (no GPU)"

    def prepare_model_input(self, images_array, history_xyz, history_rot, t0_us):
        images = np.asarray(images_array)
        if images.ndim != 5 or images.shape[0] != self.num_cameras:
            raise ValueError(
                f"FakeAdapter expects ({self.num_cameras}, T, H, W, 3), got {images.shape}"
            )
        return {
            "image_frames": images,
            "ego_history_xyz": np.asarray(history_xyz, dtype=np.float32),
            "ego_history_rot": np.asarray(history_rot, dtype=np.float32),
            "t0_us": int(t0_us),
        }

    @staticmethod
    def expected_trajectory(history_xyz, t0_us, navigation_text="", seed=None, image_mean=0.0):
        """The trajectory ``run_inference`` returns for these inputs (shape (1,1,1,H,3))."""
        x = np.linspace(0.0, 10.0, HORIZON, dtype=np.float32)
        offset = (
            float(np.asarray(history_xyz, dtype=np.float64).sum()) * 1e-3
            + float(t0_us) * 1e-9
            + len(navigation_text or "") * 1e-2
            + (0.0 if seed is None else float(seed) * 1e-3)
            + float(image_mean) * 1e-3
        )
        y = np.full(HORIZON, offset, dtype=np.float32)
        z = np.zeros(HORIZON, dtype=np.float32)
        return np.stack([x, y, z], axis=-1)[None, None, None]

    def _maybe_fail_or_sleep(self):
        if self.fail_with is not None:
            raise self.fail_with
        if self.sleep_sec:
            time.sleep(self.sleep_sec)

    def run_inference(
        self, model, processor, data,
        navigation_text=None, navigation_weight=1.0, vlm_generate_timing=None, seed=None,
    ):
        self._maybe_fail_or_sleep()
        nav_text = navigation_text or ""
        self.calls.append(("predict", nav_text, float(navigation_weight), seed))
        if vlm_generate_timing is not None:
            vlm_generate_timing.record(0.001)
        image_mean = float(np.asarray(data["image_frames"]).mean())
        pred = self.expected_trajectory(
            data["ego_history_xyz"], data["t0_us"], nav_text, seed, image_mean
        )
        extra = {
            "cot": f"fake cot nav={nav_text!r} weight={float(navigation_weight):.2f}",
            "num_traj_samples": cfg.NUM_TRAJ_SAMPLES,
        }
        return pred, extra

    def run_vqa(self, model, processor, data, question, seed=None):
        self._maybe_fail_or_sleep()
        self.calls.append(("vqa", question, seed))
        return {"answer": [f"fake answer to: {question}"], "raw_answer": [f"<raw>{question}</raw>"]}

    def extract_cot_text(self, extra):
        return str(extra.get("cot", "")) if isinstance(extra, dict) else ""

    def extract_answer_text(self, extra):
        if isinstance(extra, dict):
            answer = extra.get("answer", "")
            if isinstance(answer, (list, tuple)):
                answer = answer[0] if answer else ""
            return str(answer)
        return ""
