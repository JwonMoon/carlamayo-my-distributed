"""Encode/decode the arrays carried by the remote inference RPC.

Torch-free on purpose: the sim host runs this without torch, the inference host runs
it before handing numpy arrays to the (torch-based) adapters.

Image stacks are ``(cam, frame, H, W, 3)`` uint8 RGB arrays, exactly what
``module.loops._common.stack_frame_buffer`` produces and what
``AlpamayoAdapter.prepare_model_input`` consumes.
"""

from __future__ import annotations

import cv2
import numpy as np

from module.remote import alpamayo_inference_pb2 as pb

ENCODING_JPEG = "jpeg"
ENCODING_RAW = "raw_rgb8"
IMAGE_ENCODINGS = (ENCODING_JPEG, ENCODING_RAW)
DEFAULT_JPEG_QUALITY = 95


def array_to_tensor(array) -> pb.Tensor:
    arr = np.ascontiguousarray(np.asarray(array))
    if arr.dtype.byteorder == ">":
        arr = arr.astype(arr.dtype.newbyteorder("<"))
    return pb.Tensor(shape=list(arr.shape), dtype=arr.dtype.str, data=arr.tobytes())


def tensor_to_array(tensor: pb.Tensor) -> np.ndarray:
    dtype = np.dtype(tensor.dtype)
    arr = np.frombuffer(tensor.data, dtype=dtype)
    expected = int(np.prod(tensor.shape)) if len(tensor.shape) else arr.size
    if arr.size != expected:
        raise ValueError(
            f"Tensor payload has {arr.size} elements but shape {list(tensor.shape)} needs {expected}"
        )
    return arr.reshape(tuple(tensor.shape)).copy()


def encode_image(rgb: np.ndarray, encoding: str, jpeg_quality: int = DEFAULT_JPEG_QUALITY) -> pb.ImageFrame:
    rgb = np.asarray(rgb)
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise ValueError(f"Expected (H, W, 3) uint8 RGB image, got {rgb.shape} {rgb.dtype}")
    height, width = rgb.shape[:2]
    if encoding == ENCODING_RAW:
        data = np.ascontiguousarray(rgb).tobytes()
    elif encoding == ENCODING_JPEG:
        ok, buf = cv2.imencode(
            ".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
            [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)],
        )
        if not ok:
            raise RuntimeError("cv2.imencode failed")
        data = buf.tobytes()
    else:
        raise ValueError(f"Unknown image encoding {encoding!r}; expected one of {IMAGE_ENCODINGS}")
    return pb.ImageFrame(data=data, encoding=encoding, height=height, width=width)


def decode_image(frame: pb.ImageFrame) -> np.ndarray:
    if frame.encoding == ENCODING_RAW:
        arr = np.frombuffer(frame.data, dtype=np.uint8)
        expected = frame.height * frame.width * 3
        if arr.size != expected:
            raise ValueError(f"raw image has {arr.size} bytes, expected {expected}")
        return arr.reshape(frame.height, frame.width, 3).copy()
    if frame.encoding == ENCODING_JPEG:
        bgr = cv2.imdecode(np.frombuffer(frame.data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError("cv2.imdecode failed: corrupt JPEG payload")
        if bgr.shape[:2] != (frame.height, frame.width):
            raise ValueError(
                f"decoded JPEG is {bgr.shape[:2]}, header says {(frame.height, frame.width)}"
            )
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    raise ValueError(f"Unknown image encoding {frame.encoding!r}")


def encode_image_stack(
    images_array: np.ndarray,
    encoding: str = ENCODING_JPEG,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> pb.ImageStack:
    """``(cam, frame, H, W, 3)`` uint8 RGB -> ImageStack (camera-major, then time)."""
    images = np.asarray(images_array)
    if images.ndim != 5 or images.shape[-1] != 3:
        raise ValueError(f"Expected (cam, frame, H, W, 3) array, got {images.shape}")
    if images.dtype != np.uint8:
        raise ValueError(f"Expected uint8 images, got {images.dtype}")
    num_cameras, num_frames = images.shape[:2]
    stack = pb.ImageStack(num_cameras=num_cameras, num_frames=num_frames)
    for cam in range(num_cameras):
        for t in range(num_frames):
            stack.frames.append(encode_image(images[cam, t], encoding, jpeg_quality))
    return stack


def decode_image_stack(stack: pb.ImageStack) -> np.ndarray:
    """ImageStack -> ``(cam, frame, H, W, 3)`` uint8 RGB."""
    expected = stack.num_cameras * stack.num_frames
    if len(stack.frames) != expected:
        raise ValueError(
            f"ImageStack has {len(stack.frames)} frames but declares "
            f"{stack.num_cameras} cameras x {stack.num_frames} frames = {expected}"
        )
    if expected == 0:
        raise ValueError("ImageStack is empty")
    first = decode_image(stack.frames[0])
    out = np.empty((stack.num_cameras, stack.num_frames) + first.shape, dtype=np.uint8)
    out[0, 0] = first
    for idx in range(1, expected):
        img = decode_image(stack.frames[idx])
        if img.shape != first.shape:
            raise ValueError(f"frame {idx} is {img.shape}, frame 0 is {first.shape}")
        out[idx // stack.num_frames, idx % stack.num_frames] = img
    return out


def stack_num_bytes(stack: pb.ImageStack) -> int:
    return sum(len(f.data) for f in stack.frames)


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    """Peak signal-to-noise ratio in dB between two uint8 images (used by tests/parity)."""
    diff = np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64)
    mse = float(np.mean(diff * diff))
    if mse == 0.0:
        return float("inf")
    return 10.0 * np.log10(255.0**2 / mse)
