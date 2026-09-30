"""Version-agnostic Alpamayo adapter interface and shared helpers.

Each supported Alpamayo release (1 / 1.5 / 2) ships its own Python package, model
class, camera contract, and trajectory-sampling API. An adapter wraps one release
behind a single interface so the CARLA loops (open / closed / live-open) stay
version-agnostic. The heavy model package is imported lazily inside ``load_model``
so selecting a version, listing camera configs, and the unit tests never import
torch or a model package that is not installed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AlpamayoAdapter(ABC):
    """One Alpamayo release behind a stable CARLA-facing interface."""

    #: Public ``--version`` token, e.g. ``"1"``, ``"1.5"``, ``"2"``.
    version: str = ""
    #: Hugging Face repo id for the released weights.
    model_id: str = ""
    #: Human-readable model name for logs and video overlays.
    display_name: str = ""

    #: Ordered CARLA sensor rig: camera_name -> {x, y, z, pitch, yaw, fov}.
    #: The order defines the camera axis of ``image_frames`` fed to the model.
    source_camera_configs: dict[str, dict[str, float]] = {}
    #: Canonical camera indices matching ``source_camera_configs`` order.
    source_camera_indices: tuple[int, ...] = ()
    #: Camera position (in the spawned rig) used for trajectory visualization.
    viz_camera_slot: int = 0

    #: Capability flags gate CLI modes so unsupported combinations fail early.
    supports_navigation: bool = False
    supports_vqa: bool = False
    supports_oom_free: bool = False

    #: True for adapters that forward inference to another host; the loops then
    #: skip local-GPU-only work (VRAM prints, CUDA linalg configuration).
    is_remote: bool = False
    #: How the served model was loaded. Local adapters set these in ``load_model``;
    #: remote adapters copy them from the server's model info.
    quantization: bool = False
    oom_free: bool = False

    @property
    def num_cameras(self) -> int:
        return len(self.source_camera_configs)

    @property
    def num_traj_samples(self) -> int:
        """Trajectory samples per inference (local: module.config; remote: from the server)."""
        from module import config as cfg

        return int(cfg.NUM_TRAJ_SAMPLES)

    def runtime_summary(self) -> str:
        """One-line description of where the model runs and how much VRAM it uses."""
        try:
            import torch
        except ImportError:  # pragma: no cover - CARLA-side env without torch
            return ""
        if not torch.cuda.is_available():
            return ""
        return f"VRAM: {torch.cuda.memory_allocated() / 1024**3:.1f} GB allocated"

    @staticmethod
    def seed_everything(seed: int | None) -> None:
        """Reseed torch RNGs before sampling when ``seed`` is given (open-loop parity)."""
        if seed is None:
            return
        import torch

        torch.manual_seed(int(seed))
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(int(seed))

    @abstractmethod
    def load_model(
        self,
        use_quantization: bool = False,
        device_map: str | None = "auto",
        oom_free: bool = False,
        oom_kwargs: dict[str, Any] | None = None,
    ) -> tuple[Any, Any]:
        """Load and return ``(model, processor)`` for this release."""

    @abstractmethod
    def prepare_model_input(
        self,
        images_array: Any,
        history_xyz: Any,
        history_rot: Any,
        t0_us: int,
    ) -> dict[str, Any]:
        """Convert one CARLA frame (source-ring images + ego history) to model input."""

    @abstractmethod
    def run_inference(
        self,
        model: Any,
        processor: Any,
        data: dict[str, Any],
        navigation_text: str | None = None,
        navigation_weight: float = 1.0,
        vlm_generate_timing: Any | None = None,
        seed: int | None = None,
    ) -> tuple[Any, Any]:
        """Run trajectory inference; return ``(pred_xyz, extra)``.

        ``seed`` reseeds the sampler RNG first when given, so replaying the same input
        yields the same trajectory (used by open-loop and the parity harness).
        """

    def run_vqa(
        self,
        model: Any,
        processor: Any,
        data: dict[str, Any],
        question: str,
        seed: int | None = None,
    ) -> Any:
        """Run VQA text generation. Overridden only by versions that support it."""
        raise NotImplementedError(
            f"Alpamayo {self.version} does not support VQA."
        )

    @abstractmethod
    def extract_cot_text(self, extra: Any) -> str:
        """Return the decoded Chain-of-Causation / Chain-of-Thought text."""

    def extract_answer_text(self, extra: Any) -> str:
        """Return the decoded VQA answer text. Overridden by VQA-capable versions."""
        raise NotImplementedError(
            f"Alpamayo {self.version} does not support VQA."
        )
