import os

import numpy as np
import pytest

pytest.importorskip("pygame")

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from module.navigation_control import NavigationControlState
from module.pygame_ui import ClosedLoopPygameUI


@pytest.mark.parametrize("size,panel", [((1280, 900), 190), ((960, 675), 142), ((640, 450), 95)])
def test_panel_and_fonts_scale_with_window_width(size, panel):
    ui = ClosedLoopPygameUI(width=size[0], height=size[1], mode="navigation")
    try:
        assert ui.panel_height == panel
        assert ui.scale == pytest.approx(size[0] / 1280)
        assert ui.font.get_height() > ui.small_font.get_height()
    finally:
        ui.close()


@pytest.mark.parametrize("mode", ["normal", "navigation", "vqa", "live-open"])
def test_draw_and_capture_at_three_quarter_size(mode):
    ui = ClosedLoopPygameUI(width=960, height=675, mode=mode)
    try:
        state = NavigationControlState(mode="normal" if mode == "live-open" else mode)
        state.input_text = "Turn right in 30m | 1.5"
        state.last_error = "example error"
        frame = np.full((1080, 1920, 3), 80, dtype=np.uint8)
        ui.draw(frame, state, {"speed_kmh": 27.0, "frame": 12, "inference_time": 2.9, "steering": 0.1})
        captured = ui.capture_frame()
        assert captured.shape == (675, 960, 3)
        assert captured.max() > 0
    finally:
        ui.close()

