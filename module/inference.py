"""Version-agnostic inference helpers shared by every Alpamayo adapter.

Per-release model loading, prompt construction, and trajectory sampling live in
``module.adapters``; this module keeps only the pieces that do not depend on which
Alpamayo version is loaded, plus a re-export of the ``--version`` dispatcher.
"""

import numpy as np
import torch

from module.adapters import SUPPORTED_VERSIONS, get_adapter

SUPPORTED_CUDA_LINALG_LIBRARIES = {"default", "cusolver", "magma"}


def configure_cuda_linalg_library(library: str | None):
    """Set PyTorch's preferred CUDA linalg backend when supported."""

    if library is None:
        return None

    normalized = library.strip().lower()
    if normalized in {"", "none"}:
        return None
    if normalized not in SUPPORTED_CUDA_LINALG_LIBRARIES:
        supported = ", ".join(sorted(SUPPORTED_CUDA_LINALG_LIBRARIES))
        raise ValueError(
            f"Unsupported CUDA linalg library '{library}'. Expected one of: {supported}."
        )
    if not torch.cuda.is_available():
        return None

    preferred_linalg_library = getattr(torch.backends.cuda, "preferred_linalg_library", None)
    if preferred_linalg_library is None:
        return None
    return preferred_linalg_library(normalized)


def extract_trajectory_samples(pred_xyz):
    """Squeeze batch axes and keep xyz, returning ``(num_samples, horizon, 3)``."""
    arr = pred_xyz.detach().cpu().numpy()
    while arr.ndim > 3:
        arr = arr[0]
    if arr.ndim != 3:
        raise ValueError(f"Unexpected pred_xyz shape after squeeze: {arr.shape}")
    if arr.shape[-1] < 3:
        raise ValueError(f"Trajectory last dim must be >= 3, got {arr.shape}")
    return arr[:, :, :3]


def select_trajectory_by_prev_similarity(traj_samples, prev_traj):
    """Pick the sample closest in xy to the previously followed trajectory."""
    num_samples = traj_samples.shape[0]
    if prev_traj is None:
        return 0, [None] * num_samples

    prev_xy = prev_traj[:, :2]
    scores = []
    for i in range(num_samples):
        curr_xy = traj_samples[i, :, :2]
        n = min(len(curr_xy), len(prev_xy))
        if n <= 0:
            score = float("inf")
        else:
            score = float(np.mean(np.linalg.norm(curr_xy[:n] - prev_xy[:n], axis=1)))
        scores.append(score)

    best_idx = int(np.argmin(scores))
    return best_idx, scores


__all__ = [
    "SUPPORTED_VERSIONS",
    "configure_cuda_linalg_library",
    "extract_trajectory_samples",
    "get_adapter",
    "select_trajectory_by_prev_similarity",
]
