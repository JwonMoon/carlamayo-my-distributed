import importlib.util
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _tool():
    spec = importlib.util.spec_from_file_location("compare_predictions", ROOT / "tools" / "compare_predictions.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["compare_predictions"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write(run_dir: Path, preds, frame_ids=(3, 4, 5)):
    run_dir.mkdir(parents=True)
    np.savez_compressed(
        run_dir / "predictions.npz", predictions=preds, frame_ids=np.asarray(frame_ids),
        inference_times=np.full(len(frame_ids), 0.5, dtype=np.float32), seed=42,
    )


def test_identical_runs_pass(tmp_path, capsys):
    tool = _tool()
    preds = np.random.default_rng(0).normal(size=(3, 1, 64, 3)).astype(np.float32)
    _write(tmp_path / "a", preds)
    _write(tmp_path / "b", preds.copy())
    assert tool.main([str(tmp_path / "a"), str(tmp_path / "b")]) == 0
    report = (tmp_path / "b" / "parity.md").read_text()
    assert "bitwise identical: True" in report and "frames compared: 3" in report


def test_divergent_runs_fail_with_atol(tmp_path):
    tool = _tool()
    preds = np.zeros((3, 1, 64, 3), dtype=np.float32)
    other = preds.copy()
    other[1, 0, :, 1] += 0.05  # 5 cm lateral drift on frame 4
    _write(tmp_path / "a", preds)
    _write(tmp_path / "b", other)
    assert tool.main([str(tmp_path / "a"), str(tmp_path / "b"), "--atol", "1e-3"]) == 2
    assert tool.main([str(tmp_path / "a"), str(tmp_path / "b"), "--atol", "0.1"]) == 0
    result = tool.compare(tool.load_predictions(tmp_path / "a"), tool.load_predictions(tmp_path / "b"))
    assert result["max_abs"][1] > 0 and result["max_abs"][0] == 0
    assert abs(result["mean_xy_dist"][1] - 0.05) < 1e-6


def test_different_frames_are_rejected(tmp_path):
    tool = _tool()
    preds = np.zeros((2, 1, 64, 3), dtype=np.float32)
    _write(tmp_path / "a", preds, frame_ids=(1, 2))
    _write(tmp_path / "b", preds, frame_ids=(2, 3))
    import pytest

    with pytest.raises(SystemExit, match="different frames"):
        tool.main([str(tmp_path / "a"), str(tmp_path / "b")])
