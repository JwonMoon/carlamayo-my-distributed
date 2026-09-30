# 분리 구현 로드맵

[distributed-architecture.md](distributed-architecture.md)의 설계를 코드로 옮기는 순서다.
각 단계는 **CI(`python -m pytest -q tests`)가 계속 통과하도록** 배치했고, 앞 단계가 뒤 단계의
전제다. 단계가 끝날 때마다 [changes-from-upstream.md](changes-from-upstream.md)에 무엇을 어디에
왜 바꿨는지 적는다.

상태 표기: ☐ 미착수, ◐ 진행 중, ☑ 완료

---

## ☐ 1. torch 디커플링 (A에서 torch 없이 import 가능하게)

| 파일 | 변경 |
|---|---|
| `module/inference.py` | 최상단 `import torch` 제거. `configure_cuda_linalg_library` 안에서 지연 import. `extract_trajectory_samples`는 `hasattr(pred_xyz, "detach")`면 `.detach().cpu().numpy()`, 아니면 `np.asarray(pred_xyz, dtype=np.float32)` |
| `module/visualization.py` | `import torch` 제거. 58행 `isinstance(..., torch.Tensor)`를 `hasattr(pred_xyz, "detach")`로 |
| `module/adapters/base.py` | `is_remote: bool = False`, `runtime_summary() -> str`(기본 구현: torch 지연 import 후 VRAM 문자열, CUDA 없으면 빈 문자열), `run_inference(..., seed=None)`·`run_vqa(..., seed=None)` 인자 추가 |
| `module/adapters/alpamayo_{r1,1_5,2}.py` | `seed`가 주어지면 샘플링 직전 `torch.manual_seed`·`torch.cuda.manual_seed_all` |
| `module/loops/closed_loop.py`, `live_open_loop.py`, `open_loop.py` | `import torch` 제거. VRAM 출력을 `print(adapter.runtime_summary())`로. `open_loop.py:89`의 `torch.cuda.manual_seed_all(42)`를 `run_inference(..., seed=42)`로 |
| `tests/test_inference_utils.py` | numpy 입력 케이스 추가 |
| 검증 | `python -c "import module.loops.closed_loop"`가 torch 없는 venv에서 성공(단, `carla` 필요). CI 통과 |

## ☐ 2. proto + codec

| 항목 | 내용 |
|---|---|
| `proto/alpamayo_inference.proto` | [distributed-architecture.md §7](distributed-architecture.md) 그대로 |
| `module/remote/codec.py` | `encode_image_stack(images_array, encoding, jpeg_quality)`, `decode_image_stack(stack) -> np.ndarray`, `tensor_to_proto`, `proto_to_tensor`. **torch·carla 비의존** |
| 생성 스텁 | `python -m grpc_tools.protoc -I proto --python_out=module/remote --grpc_python_out=module/remote proto/alpamayo_inference.proto` 결과를 커밋 |
| `tests/test_remote_codec.py` | raw 왕복 비트 동일, JPEG q95 왕복 PSNR > 40 dB·shape/dtype 유지·RGB 채널 순서 보존, Tensor 왕복 `(16,3)`/`(16,3,3)`/`(1,1,1,64,3)`, 카메라·프레임 수 불일치 거부 |

## ☐ 3. FakeAdapter + 서버 서비서 + in-process 테스트

| 항목 | 내용 |
|---|---|
| `module/remote/fake_adapter.py` | `AlpamayoAdapter` 서브클래스. 4카메라 리그 광고, `pred_xyz (1,1,1,64,3)`를 `history_xyz`·`t0_us`·`navigation_text`·`seed`의 결정적 함수로 반환, `extra={"cot":..., "answer":...}`. 테스트 전용 |
| `module/remote/server.py` | `AlpamayoServicer(adapter, model, processor)`: `GetModelInfo`, `Predict`, `AnswerQuestion`. 모델 호출 `threading.Lock`, 두 번째 동시 요청은 `RESOURCE_EXHAUSTED`, 워밍업 전 `FAILED_PRECONDITION`. cuSOLVER→MAGMA 재시도(`closed_loop.py:244-256` 로직)를 여기로 이동. `grpc_health` 등록. `serve(adapter, host, port, max_message_mb, ...)` |
| `tests/test_remote_server.py` | `grpc.server`를 `localhost:0`에 띄우는 fixture. ModelInfo 내용, Predict 왕복, VQA, 동시성 거절, 미워밍업 거절, `FakeAdapter(sleep=2)` + 0.5 s deadline → `DEADLINE_EXCEEDED` |

## ☐ 4. RemoteAlpamayoAdapter + 런처 플래그

| 항목 | 내용 |
|---|---|
| `module/remote/client.py` | `RemoteAlpamayoAdapter(expected_version, target, image_encoding, jpeg_quality, rpc_timeout_sec, connect_timeout_sec)`. `load_model()`: 채널 생성 → `channel_ready_future` → `GetModelInfo` → 버전·프로토콜·`NUM_FRAMES`·`NUM_HISTORY`·`IMG_*`·`NUM_TRAJ_SAMPLES` 검증 → 리그/capability/서버 옵션 채움 → `(None, None)` 반환. `prepare_model_input()`: 인코딩까지 수행(워커 스레드에서 돌게). `run_inference()`: `Predict` 호출, numpy 반환, `extra={"cot","timings"}`. `run_vqa()`, `extract_*`. `grpc.RpcError` → `RemoteInferenceError`. `runtime_summary()`는 서버 VRAM·옵션 문자열 |
| `module/adapters/__init__.py` | 버전 별칭 정규화를 `normalize_version()`으로 노출(클라이언트 검증에 재사용) |
| `carlamayo.py` | `--inference-server HOST:PORT`, `--image-encoding {jpeg,raw}`(기본 jpeg), `--jpeg-quality 95`, `--rpc-timeout-sec 120`, `--rpc-connect-timeout-sec 30`. `build_adapter(args)`: 원격이면 `RemoteAlpamayoAdapter`, 아니면 `get_adapter`. 원격일 때 `--quantization/--oom-free*/--device-map≠auto/--cuda-linalg-library≠magma`는 `parser.error`("서버 플래그입니다") |
| `module/loops/open_loop.py` | `_load_model`을 `camera_order` 계산(50~51행)보다 앞으로 이동 |
| `module/loops/closed_loop.py`, `live_open_loop.py` | 96~99행 등 quantization/oom 출력은 `adapter.quantization`·`adapter.oom_free` 속성에서 읽음. `_check_capabilities`는 그대로(capability가 ModelInfo에서 옴) |
| `tests/test_carlamayo_launcher.py`, `tests/test_remote_client.py` | 플래그 파싱, 원격+서버 플래그 조합 거부, `build_adapter`가 연결 없이 원격 어댑터 반환, FakeAdapter 서버 상대로 `load_model`이 리그를 동일하게 채우는지, 버전 불일치 시 종료, deadline 매핑 |
| import 가드 테스트 | `import module.remote.client` 후 `sys.modules`에 `torch`·`carla`가 없음을 확인 |

## ☐ 5. `alpamayo_server.py`

| 항목 | 내용 |
|---|---|
| CLI | `--version {1,1.5,2}`(필수), `--host 0.0.0.0`, `--port 50051`, `--quantization`, `--oom-free`, `--oom-free-headroom-gb/--oom-free-margin/--oom-free-resident`, `--device-map auto`, `--cuda-linalg-library magma`, `--no-warmup`, `--max-message-mb 512` |
| 시작 순서 | `get_adapter` → `configure_cuda_linalg_library` → `load_model`(OOM kwargs는 `_common.collect_oom_kwargs` 재사용) → 워밍업 1회(0 이미지 + 0 이력으로 `Predict` 경로 실행, flash-attn/cuBLAS 커널 컴파일) → `warmed_up=True`, health SERVING → serve |
| 로그 | 요청마다 `request_id`, frame, revisions, 디코드/전처리/추론 시간, VRAM |
| CFG/VQA | `Predict`의 `navigation_weight`를 그대로 `run_inference`에, `AnswerQuestion`은 `run_vqa`에 |

## ☐ 6. stale trajectory 안전장치

| 항목 | 내용 |
|---|---|
| `module/config.py` | `TRAJECTORY_MAX_AGE_SEC = 3.0` |
| `module/loops/closed_loop.py` | PID 적용 직전 `time.time() - current_trajectory_ts > cfg.TRAJECTORY_MAX_AGE_SEC`면 `current_trajectory = None`(→ 기존 정지 분기). 동기·비동기 모두 적용 |
| `tests/` | 나이 계산 헬퍼를 순수 함수로 빼서 테스트 |

## ☐ 7. pygame UI 개선 (A 전용, RPC 무관)

| 항목 | 내용 |
|---|---|
| `carlamayo.py` | `--pygame-ui`를 기본 True로, `--no-pygame-ui` 추가. `--start-paused` 추가 |
| `module/loops/closed_loop.py:90` | `start_paused = args.start_paused if 명시 else (mode != "normal" and 초기 프롬프트 없음)` |
| `module/loops/live_open_loop.py` | closed-loop의 UI 생성·갱신·기록 코드를 `module/loops/_ui.py` 공통 헬퍼로 추출해 양쪽에서 사용. live-open은 입력창 없이 상태 패널만 |
| `module/pygame_ui.py` | 모드 `live-open` 패널 텍스트 추가 |
| 문서 | navigation-mode.md, vqa-mode.md의 "starts paused" 문구 갱신 |

## ☐ 8. 환경 분리

| 파일 | 내용 |
|---|---|
| `requirements-sim.txt` | numpy, opencv-python, pygame, scipy, pillow, carla==0.9.16, grpcio, protobuf |
| `requirements-carla.txt` | 호환용: `-r requirements-sim.txt` 한 줄 |
| `requirements-inference.txt` | 기존 `requirements-alpamayo.txt` 내용 + grpcio, grpcio-health-checking, protobuf |
| `requirements-alpamayo.txt` | 호환용: `-r requirements-inference.txt` |
| `pyproject.toml` | dependencies에 grpcio, protobuf; dev에 grpcio-tools. `uv.lock`은 B에서 재생성(flash-attn 때문에 CI 불가) |
| `.github/workflows/ci.yml` | grpcio, grpcio-tools, protobuf 설치. 스텁 재생성 후 `git diff --exit-code module/remote/*_pb2*.py` |
| `docs/environment-setup.md` | §3 "Combined" 환경을 두 호스트 절차로 교체 |

## ☐ 9. AWS 배포 자산

| 파일 | 내용 |
|---|---|
| `deploy/aws/README.md` | 인스턴스 표(A g5.2xlarge 172.31.38.219 / B g6e.xlarge 172.31.20.213), AMI(Deep Learning AMI 또는 Ubuntu 22.04 + NVIDIA 드라이버 + Vulkan), 보안그룹 규칙표, A↔B SSH 키 등록, DCV 접속, SSH 포트포워딩 |
| `deploy/systemd/alpamayo-server.service` | `ExecStart=.../a_venv/bin/python alpamayo_server.py --version 1.5 --host 172.31.20.213`, `Restart=on-failure`, `TimeoutStartSec=900`, `Environment=HF_HOME=...` |
| `deploy/scripts/` | `setup-sim-host.sh`, `setup-inference-host.sh`, `sync-dataset-to-inference-host.sh`(rsync A→B) |
| `docs/cheatsheet.md` | 실제 명령으로 확정 |

## ☐ 10. 검증

| 항목 | 내용 |
|---|---|
| `tools/parity_open_loop.py` | 같은 `carla_data/`, `seed=42`로 (1) B 로컬 (2) A 원격(raw) (3) A 원격(JPEG) 실행, 각 `predictions.npz` 저장 |
| `tools/compare_predictions.py` | 프레임별 max abs diff, minADE 차이 표. raw는 ~1e-6 이내 기대, JPEG 차이는 기록 |
| closed-loop 스모크 | sync/async × normal/navigation(weight 1.0, 1.5)/vqa 각 2분 주행, 충돌·리스폰 동작, 서버 재시작 중 클라이언트 생존, 궤적 나이 초과 시 정지 |
| live-open 스모크 | async, UI 표시 |
| 성능 CSV | 요청당 인코딩/전송/디코드/추론/총 시간, 요청 크기, A CPU 사용률, B VRAM. `docs/distributed-architecture.md`에 "실측" 절 추가 |
