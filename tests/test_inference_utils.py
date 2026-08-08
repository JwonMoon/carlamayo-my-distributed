import numpy as np
import pytest
import torch

from module import inference


def test_configure_cuda_linalg_library_validates_choice():
    with pytest.raises(ValueError, match="Unsupported CUDA linalg library"):
        inference.configure_cuda_linalg_library("not-a-backend")
    # Unset / disabled inputs are accepted and return None.
    assert inference.configure_cuda_linalg_library(None) is None
    assert inference.configure_cuda_linalg_library("none") is None


def test_extract_trajectory_samples_squeezes_batch_axes_and_keeps_xyz_only():
    pred_xyz = torch.arange(1 * 1 * 2 * 3 * 4, dtype=torch.float32).reshape(1, 1, 2, 3, 4)
    samples = inference.extract_trajectory_samples(pred_xyz)
    assert samples.shape == (2, 3, 3)
    np.testing.assert_allclose(samples, pred_xyz.numpy()[0, 0, :, :, :3])


def test_extract_trajectory_samples_rejects_degenerate_shapes():
    with pytest.raises(ValueError):
        inference.extract_trajectory_samples(torch.zeros(2, 3, 2))


def test_select_trajectory_by_prev_similarity_prefers_closest_xy_path():
    previous = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float32)
    candidates = np.array(
        [
            [[0.0, 2.0, 0.0], [1.0, 2.0, 0.0]],
            [[0.0, 0.1, 0.0], [1.0, 0.1, 0.0]],
        ],
        dtype=np.float32,
    )
    best_idx, scores = inference.select_trajectory_by_prev_similarity(candidates, previous)
    assert best_idx == 1
    assert scores[1] < scores[0]


def test_select_trajectory_defaults_to_first_without_history():
    candidates = np.zeros((3, 2, 3), dtype=np.float32)
    best_idx, scores = inference.select_trajectory_by_prev_similarity(candidates, None)
    assert best_idx == 0
    assert scores == [None, None, None]
