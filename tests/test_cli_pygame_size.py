import pytest


def test_pygame_size_flag_overrides_config(monkeypatch):
    import carlamayo
    from module import config as cfg

    monkeypatch.setattr(cfg, "PYGAME_WINDOW_WIDTH", 960)
    monkeypatch.setattr(cfg, "PYGAME_WINDOW_HEIGHT", 675)
    args = carlamayo.build_parser().parse_args(["--loop", "closed", "--version", "1.5", "--pygame-size", "1280x900"])
    assert carlamayo.apply_pygame_size(args) == (1280, 900)
    assert (cfg.PYGAME_WINDOW_WIDTH, cfg.PYGAME_WINDOW_HEIGHT) == (1280, 900)
    args = carlamayo.build_parser().parse_args(["--loop", "closed", "--version", "1.5"])
    assert carlamayo.apply_pygame_size(args) == (1280, 900)  # no flag: untouched
    with pytest.raises(ValueError, match="WxH"):
        carlamayo.parse_pygame_size("big")
    with pytest.raises(ValueError, match="too small"):
        carlamayo.parse_pygame_size("100x100")
