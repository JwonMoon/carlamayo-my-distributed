"""The CARLA-side (sim host) modules must import without torch installed.

``sys.modules["torch"] = None`` makes any ``import torch`` raise ImportError, which
simulates the sim-host environment where only the simulator packages are installed.
Adapters that wrap a local model (``alpamayo_r1``, ``alpamayo_1_5``, ``alpamayo_2``)
are allowed to import torch; everything the loops need on the sim host is not.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

TORCH_FREE_MODULES = [
    "module.config",
    "module.inference",
    "module.visualization",
    "module.adapters",
    "module.adapters.base",
    "module.adapters._rigs",
    "module.adapters._text",
    "module.loops._common",
    "module.open_loop_dataset",
    "module.navigation_control",
    "module.respawn_control",
    "module.vlm_generate_optimization",
    "module.data_collection",
    "module.run_dir",
    "module.remote.codec",
    "module.remote.client",
    "carlamayo",
]


@pytest.mark.parametrize("module_name", TORCH_FREE_MODULES)
def test_module_imports_without_torch(module_name):
    code = (
        "import sys; sys.modules['torch'] = None; "
        f"import {module_name}; "
        "assert 'torch' not in sys.modules or sys.modules['torch'] is None"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_extract_trajectory_samples_works_without_torch():
    code = (
        "import sys; sys.modules['torch'] = None; "
        "import numpy as np; from module.inference import extract_trajectory_samples; "
        "out = extract_trajectory_samples(np.zeros((1, 1, 2, 5, 4), dtype=np.float32)); "
        "assert out.shape == (2, 5, 3), out.shape"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
