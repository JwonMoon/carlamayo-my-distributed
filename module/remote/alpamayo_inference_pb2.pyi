from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetModelInfoRequest(_message.Message):
    __slots__ = ("client_protocol_version",)
    CLIENT_PROTOCOL_VERSION_FIELD_NUMBER: _ClassVar[int]
    client_protocol_version: str
    def __init__(self, client_protocol_version: _Optional[str] = ...) -> None: ...

class CameraConfig(_message.Message):
    __slots__ = ("name", "x", "y", "z", "pitch", "yaw", "fov")
    NAME_FIELD_NUMBER: _ClassVar[int]
    X_FIELD_NUMBER: _ClassVar[int]
    Y_FIELD_NUMBER: _ClassVar[int]
    Z_FIELD_NUMBER: _ClassVar[int]
    PITCH_FIELD_NUMBER: _ClassVar[int]
    YAW_FIELD_NUMBER: _ClassVar[int]
    FOV_FIELD_NUMBER: _ClassVar[int]
    name: str
    x: float
    y: float
    z: float
    pitch: float
    yaw: float
    fov: float
    def __init__(self, name: _Optional[str] = ..., x: _Optional[float] = ..., y: _Optional[float] = ..., z: _Optional[float] = ..., pitch: _Optional[float] = ..., yaw: _Optional[float] = ..., fov: _Optional[float] = ...) -> None: ...

class ModelInfo(_message.Message):
    __slots__ = ("protocol_version", "version", "model_id", "display_name", "cameras", "camera_indices", "viz_camera_slot", "supports_navigation", "supports_vqa", "supports_oom_free", "quantization", "oom_free", "device_map", "num_frames", "num_history", "img_height", "img_width", "num_traj_samples", "warmed_up", "vram_allocated_gb", "server_git_sha", "image_encodings")
    PROTOCOL_VERSION_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    CAMERAS_FIELD_NUMBER: _ClassVar[int]
    CAMERA_INDICES_FIELD_NUMBER: _ClassVar[int]
    VIZ_CAMERA_SLOT_FIELD_NUMBER: _ClassVar[int]
    SUPPORTS_NAVIGATION_FIELD_NUMBER: _ClassVar[int]
    SUPPORTS_VQA_FIELD_NUMBER: _ClassVar[int]
    SUPPORTS_OOM_FREE_FIELD_NUMBER: _ClassVar[int]
    QUANTIZATION_FIELD_NUMBER: _ClassVar[int]
    OOM_FREE_FIELD_NUMBER: _ClassVar[int]
    DEVICE_MAP_FIELD_NUMBER: _ClassVar[int]
    NUM_FRAMES_FIELD_NUMBER: _ClassVar[int]
    NUM_HISTORY_FIELD_NUMBER: _ClassVar[int]
    IMG_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    IMG_WIDTH_FIELD_NUMBER: _ClassVar[int]
    NUM_TRAJ_SAMPLES_FIELD_NUMBER: _ClassVar[int]
    WARMED_UP_FIELD_NUMBER: _ClassVar[int]
    VRAM_ALLOCATED_GB_FIELD_NUMBER: _ClassVar[int]
    SERVER_GIT_SHA_FIELD_NUMBER: _ClassVar[int]
    IMAGE_ENCODINGS_FIELD_NUMBER: _ClassVar[int]
    protocol_version: str
    version: str
    model_id: str
    display_name: str
    cameras: _containers.RepeatedCompositeFieldContainer[CameraConfig]
    camera_indices: _containers.RepeatedScalarFieldContainer[int]
    viz_camera_slot: int
    supports_navigation: bool
    supports_vqa: bool
    supports_oom_free: bool
    quantization: bool
    oom_free: bool
    device_map: str
    num_frames: int
    num_history: int
    img_height: int
    img_width: int
    num_traj_samples: int
    warmed_up: bool
    vram_allocated_gb: float
    server_git_sha: str
    image_encodings: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, protocol_version: _Optional[str] = ..., version: _Optional[str] = ..., model_id: _Optional[str] = ..., display_name: _Optional[str] = ..., cameras: _Optional[_Iterable[_Union[CameraConfig, _Mapping]]] = ..., camera_indices: _Optional[_Iterable[int]] = ..., viz_camera_slot: _Optional[int] = ..., supports_navigation: _Optional[bool] = ..., supports_vqa: _Optional[bool] = ..., supports_oom_free: _Optional[bool] = ..., quantization: _Optional[bool] = ..., oom_free: _Optional[bool] = ..., device_map: _Optional[str] = ..., num_frames: _Optional[int] = ..., num_history: _Optional[int] = ..., img_height: _Optional[int] = ..., img_width: _Optional[int] = ..., num_traj_samples: _Optional[int] = ..., warmed_up: _Optional[bool] = ..., vram_allocated_gb: _Optional[float] = ..., server_git_sha: _Optional[str] = ..., image_encodings: _Optional[_Iterable[str]] = ...) -> None: ...

class Tensor(_message.Message):
    __slots__ = ("shape", "dtype", "data")
    SHAPE_FIELD_NUMBER: _ClassVar[int]
    DTYPE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    shape: _containers.RepeatedScalarFieldContainer[int]
    dtype: str
    data: bytes
    def __init__(self, shape: _Optional[_Iterable[int]] = ..., dtype: _Optional[str] = ..., data: _Optional[bytes] = ...) -> None: ...

class ImageFrame(_message.Message):
    __slots__ = ("data", "encoding", "height", "width")
    DATA_FIELD_NUMBER: _ClassVar[int]
    ENCODING_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    data: bytes
    encoding: str
    height: int
    width: int
    def __init__(self, data: _Optional[bytes] = ..., encoding: _Optional[str] = ..., height: _Optional[int] = ..., width: _Optional[int] = ...) -> None: ...

class ImageStack(_message.Message):
    __slots__ = ("num_cameras", "num_frames", "frames")
    NUM_CAMERAS_FIELD_NUMBER: _ClassVar[int]
    NUM_FRAMES_FIELD_NUMBER: _ClassVar[int]
    FRAMES_FIELD_NUMBER: _ClassVar[int]
    num_cameras: int
    num_frames: int
    frames: _containers.RepeatedCompositeFieldContainer[ImageFrame]
    def __init__(self, num_cameras: _Optional[int] = ..., num_frames: _Optional[int] = ..., frames: _Optional[_Iterable[_Union[ImageFrame, _Mapping]]] = ...) -> None: ...

class ClientMeta(_message.Message):
    __slots__ = ("request_id", "frame", "prompt_revision", "respawn_revision", "run_id")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    FRAME_FIELD_NUMBER: _ClassVar[int]
    PROMPT_REVISION_FIELD_NUMBER: _ClassVar[int]
    RESPAWN_REVISION_FIELD_NUMBER: _ClassVar[int]
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    frame: int
    prompt_revision: int
    respawn_revision: int
    run_id: str
    def __init__(self, request_id: _Optional[str] = ..., frame: _Optional[int] = ..., prompt_revision: _Optional[int] = ..., respawn_revision: _Optional[int] = ..., run_id: _Optional[str] = ...) -> None: ...

class PredictRequest(_message.Message):
    __slots__ = ("meta", "images", "history_xyz", "history_rot", "t0_us", "navigation_text", "navigation_weight", "seed")
    META_FIELD_NUMBER: _ClassVar[int]
    IMAGES_FIELD_NUMBER: _ClassVar[int]
    HISTORY_XYZ_FIELD_NUMBER: _ClassVar[int]
    HISTORY_ROT_FIELD_NUMBER: _ClassVar[int]
    T0_US_FIELD_NUMBER: _ClassVar[int]
    NAVIGATION_TEXT_FIELD_NUMBER: _ClassVar[int]
    NAVIGATION_WEIGHT_FIELD_NUMBER: _ClassVar[int]
    SEED_FIELD_NUMBER: _ClassVar[int]
    meta: ClientMeta
    images: ImageStack
    history_xyz: Tensor
    history_rot: Tensor
    t0_us: int
    navigation_text: str
    navigation_weight: float
    seed: int
    def __init__(self, meta: _Optional[_Union[ClientMeta, _Mapping]] = ..., images: _Optional[_Union[ImageStack, _Mapping]] = ..., history_xyz: _Optional[_Union[Tensor, _Mapping]] = ..., history_rot: _Optional[_Union[Tensor, _Mapping]] = ..., t0_us: _Optional[int] = ..., navigation_text: _Optional[str] = ..., navigation_weight: _Optional[float] = ..., seed: _Optional[int] = ...) -> None: ...

class Timings(_message.Message):
    __slots__ = ("decode_sec", "prepare_sec", "inference_sec", "total_sec", "vlm_generate_calls", "vlm_generate_last_sec", "gpu_mem_allocated_gb", "gpu_mem_peak_gb")
    DECODE_SEC_FIELD_NUMBER: _ClassVar[int]
    PREPARE_SEC_FIELD_NUMBER: _ClassVar[int]
    INFERENCE_SEC_FIELD_NUMBER: _ClassVar[int]
    TOTAL_SEC_FIELD_NUMBER: _ClassVar[int]
    VLM_GENERATE_CALLS_FIELD_NUMBER: _ClassVar[int]
    VLM_GENERATE_LAST_SEC_FIELD_NUMBER: _ClassVar[int]
    GPU_MEM_ALLOCATED_GB_FIELD_NUMBER: _ClassVar[int]
    GPU_MEM_PEAK_GB_FIELD_NUMBER: _ClassVar[int]
    decode_sec: float
    prepare_sec: float
    inference_sec: float
    total_sec: float
    vlm_generate_calls: int
    vlm_generate_last_sec: float
    gpu_mem_allocated_gb: float
    gpu_mem_peak_gb: float
    def __init__(self, decode_sec: _Optional[float] = ..., prepare_sec: _Optional[float] = ..., inference_sec: _Optional[float] = ..., total_sec: _Optional[float] = ..., vlm_generate_calls: _Optional[int] = ..., vlm_generate_last_sec: _Optional[float] = ..., gpu_mem_allocated_gb: _Optional[float] = ..., gpu_mem_peak_gb: _Optional[float] = ...) -> None: ...

class PredictResponse(_message.Message):
    __slots__ = ("meta", "pred_xyz", "cot_text", "timings")
    META_FIELD_NUMBER: _ClassVar[int]
    PRED_XYZ_FIELD_NUMBER: _ClassVar[int]
    COT_TEXT_FIELD_NUMBER: _ClassVar[int]
    TIMINGS_FIELD_NUMBER: _ClassVar[int]
    meta: ClientMeta
    pred_xyz: Tensor
    cot_text: str
    timings: Timings
    def __init__(self, meta: _Optional[_Union[ClientMeta, _Mapping]] = ..., pred_xyz: _Optional[_Union[Tensor, _Mapping]] = ..., cot_text: _Optional[str] = ..., timings: _Optional[_Union[Timings, _Mapping]] = ...) -> None: ...

class VqaRequest(_message.Message):
    __slots__ = ("meta", "images", "history_xyz", "history_rot", "t0_us", "question", "seed")
    META_FIELD_NUMBER: _ClassVar[int]
    IMAGES_FIELD_NUMBER: _ClassVar[int]
    HISTORY_XYZ_FIELD_NUMBER: _ClassVar[int]
    HISTORY_ROT_FIELD_NUMBER: _ClassVar[int]
    T0_US_FIELD_NUMBER: _ClassVar[int]
    QUESTION_FIELD_NUMBER: _ClassVar[int]
    SEED_FIELD_NUMBER: _ClassVar[int]
    meta: ClientMeta
    images: ImageStack
    history_xyz: Tensor
    history_rot: Tensor
    t0_us: int
    question: str
    seed: int
    def __init__(self, meta: _Optional[_Union[ClientMeta, _Mapping]] = ..., images: _Optional[_Union[ImageStack, _Mapping]] = ..., history_xyz: _Optional[_Union[Tensor, _Mapping]] = ..., history_rot: _Optional[_Union[Tensor, _Mapping]] = ..., t0_us: _Optional[int] = ..., question: _Optional[str] = ..., seed: _Optional[int] = ...) -> None: ...

class VqaResponse(_message.Message):
    __slots__ = ("meta", "answer", "raw_answer", "timings")
    META_FIELD_NUMBER: _ClassVar[int]
    ANSWER_FIELD_NUMBER: _ClassVar[int]
    RAW_ANSWER_FIELD_NUMBER: _ClassVar[int]
    TIMINGS_FIELD_NUMBER: _ClassVar[int]
    meta: ClientMeta
    answer: str
    raw_answer: str
    timings: Timings
    def __init__(self, meta: _Optional[_Union[ClientMeta, _Mapping]] = ..., answer: _Optional[str] = ..., raw_answer: _Optional[str] = ..., timings: _Optional[_Union[Timings, _Mapping]] = ...) -> None: ...
