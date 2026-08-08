"""Canonical CARLA camera rigs for the Alpamayo releases.

Camera keys are the canonical Alpamayo camera names and are listed in ascending
canonical camera-index order, which is the order the model consumes on the camera
axis of ``image_frames``. Poses are in the CARLA ego frame (x forward, y right,
z up); ``fov`` is the horizontal field of view in degrees, matching each camera's
nominal real-rig FOV.
"""


def _cam(x: float, y: float, yaw: float, fov: int) -> dict[str, float]:
    return {"x": x, "y": y, "z": 2.4, "pitch": 0.0, "yaw": yaw, "fov": fov}


# Alpamayo 1 (R1) and 1.5 both consume this four-camera set: canonical indices
# [0, 1, 2, 6] = cross-left, front-wide, cross-right, front-tele.
FOUR_CAMERA_RIG = {
    "camera_cross_left_120fov": _cam(1.0, -0.5, -60.0, 120),
    "camera_front_wide_120fov": _cam(1.5, 0.0, 0.0, 120),
    "camera_cross_right_120fov": _cam(1.0, 0.5, 60.0, 120),
    "camera_front_tele_30fov": _cam(1.5, 0.0, 0.0, 30),
}
FOUR_CAMERA_INDICES = (0, 1, 2, 6)

# Alpamayo 2 consumes the full seven-camera PhysicalAI source ring; each task then
# selects its fixed six-camera profile from this ring.
SEVEN_CAMERA_RIG = {
    "camera_cross_left_120fov": _cam(1.0, -0.5, -60.0, 120),
    "camera_front_wide_120fov": _cam(1.5, 0.0, 0.0, 120),
    "camera_cross_right_120fov": _cam(1.0, 0.5, 60.0, 120),
    "camera_rear_left_70fov": _cam(-0.5, -0.5, -150.0, 70),
    "camera_rear_tele_30fov": _cam(-1.5, 0.0, 180.0, 30),
    "camera_rear_right_70fov": _cam(-0.5, 0.5, 150.0, 70),
    "camera_front_tele_30fov": _cam(1.5, 0.0, 0.0, 30),
}
SEVEN_CAMERA_INDICES = (0, 1, 2, 3, 4, 5, 6)

# The front-wide camera sits at position 1 in both rigs; it is the view used for
# trajectory projection overlays.
FRONT_WIDE_SLOT = 1
