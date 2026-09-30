import numpy as np
import pytest

from module.remote import alpamayo_inference_pb2 as pb
from module.remote import codec


def _natural_stack(cams=4, frames=4, h=64, w=96, seed=0):
    """Smooth, image-like content so JPEG behaves as it does on camera frames."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    stack = np.empty((cams, frames, h, w, 3), dtype=np.uint8)
    for c in range(cams):
        for t in range(frames):
            base = np.stack(
                [
                    128 + 100 * np.sin(xx / (8.0 + c) + t),
                    128 + 100 * np.cos(yy / (6.0 + t) + c),
                    128 + 60 * np.sin((xx + yy) / 10.0),
                ],
                axis=-1,
            )
            noise = rng.normal(0, 2, size=base.shape)
            stack[c, t] = np.clip(base + noise, 0, 255).astype(np.uint8)
    return stack


def test_raw_stack_roundtrip_is_bitwise_identical():
    stack = _natural_stack()
    encoded = codec.encode_image_stack(stack, encoding=codec.ENCODING_RAW)
    assert encoded.num_cameras == 4 and encoded.num_frames == 4
    assert len(encoded.frames) == 16
    assert codec.stack_num_bytes(encoded) == stack.nbytes
    decoded = codec.decode_image_stack(encoded)
    assert decoded.shape == stack.shape and decoded.dtype == np.uint8
    np.testing.assert_array_equal(decoded, stack)


def test_jpeg_stack_roundtrip_keeps_shape_order_and_quality():
    stack = _natural_stack()
    encoded = codec.encode_image_stack(stack, encoding=codec.ENCODING_JPEG, jpeg_quality=95)
    assert codec.stack_num_bytes(encoded) < stack.nbytes / 2
    decoded = codec.decode_image_stack(encoded)
    assert decoded.shape == stack.shape and decoded.dtype == np.uint8
    for c in range(4):
        for t in range(4):
            assert codec.psnr(stack[c, t], decoded[c, t]) > 40.0


def test_jpeg_preserves_rgb_channel_order():
    img = np.zeros((32, 48, 3), dtype=np.uint8)
    img[..., 0], img[..., 1], img[..., 2] = 200, 30, 90  # R, G, B
    stack = img[None, None]
    decoded = codec.decode_image_stack(codec.encode_image_stack(stack, codec.ENCODING_JPEG))
    means = decoded[0, 0].reshape(-1, 3).mean(axis=0)
    assert abs(means[0] - 200) < 4 and abs(means[1] - 30) < 4 and abs(means[2] - 90) < 4


def test_encode_rejects_bad_inputs():
    with pytest.raises(ValueError, match="cam, frame, H, W, 3"):
        codec.encode_image_stack(np.zeros((4, 64, 96, 3), dtype=np.uint8))
    with pytest.raises(ValueError, match="uint8"):
        codec.encode_image_stack(np.zeros((1, 1, 8, 8, 3), dtype=np.float32))
    with pytest.raises(ValueError, match="Unknown image encoding"):
        codec.encode_image_stack(np.zeros((1, 1, 8, 8, 3), dtype=np.uint8), encoding="png")


def test_decode_rejects_inconsistent_stack():
    stack = codec.encode_image_stack(np.zeros((2, 2, 8, 8, 3), dtype=np.uint8), codec.ENCODING_RAW)
    stack.num_frames = 3  # declares 6 frames, carries 4
    with pytest.raises(ValueError, match="declares"):
        codec.decode_image_stack(stack)
    with pytest.raises(ValueError, match="empty"):
        codec.decode_image_stack(pb.ImageStack(num_cameras=0, num_frames=0))


@pytest.mark.parametrize(
    "array",
    [
        np.arange(16 * 3, dtype=np.float32).reshape(16, 3),
        np.eye(3, dtype=np.float32)[None].repeat(16, axis=0),
        np.random.default_rng(1).normal(size=(1, 1, 1, 64, 3)).astype(np.float32),
        np.array([1, 2, 3], dtype=np.int64),
    ],
)
def test_tensor_roundtrip(array):
    tensor = codec.array_to_tensor(array)
    back = codec.tensor_to_array(tensor)
    assert back.shape == array.shape and back.dtype == array.dtype
    np.testing.assert_array_equal(back, array)
    assert back.flags.writeable


def test_tensor_rejects_size_mismatch():
    tensor = codec.array_to_tensor(np.zeros((2, 3), dtype=np.float32))
    tensor.shape[:] = [2, 4]
    with pytest.raises(ValueError, match="needs 8"):
        codec.tensor_to_array(tensor)
