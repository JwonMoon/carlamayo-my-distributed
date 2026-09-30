# 업스트림 대비 변경 기록

- 업스트림: `https://github.com/aveeslab/Carlamayo`, 리모트 이름 `upstream`
- 기준 커밋: `e6372ea` (Support Alpamayo 1 / 1.5 / 2 via --version and add a unified live-open-loop launcher)
- 이 저장소의 목적: 위 코드를 **CARLA 인스턴스 / Alpamayo 인스턴스로 분리 실행**하도록 개조

## 기록 규칙

1. 업스트림 코드를 고치거나 파일을 추가하는 커밋마다 아래 표에 한 줄 이상 추가한다.
2. "이유" 열에는 어떤 기능을 위해서인지 적고, 설계 근거가 있으면 [ADR](adr/README.md) 번호를 단다.
3. 로드맵 단계 번호([distributed-roadmap.md](distributed-roadmap.md))를 함께 적어 진행 상황을 추적한다.
4. 업스트림을 merge한 경우도 한 줄로 남긴다(어느 커밋까지 따라갔는지).

## 검증 기록

| 날짜 | 조건 | 결과 |
|---|---|---|
| 2026-09-30 | 가져온 직후, CI와 같은 의존성(CPU torch, numpy, scipy, pillow, opencv-headless, pytest), `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests` | **55 passed** |
| 2026-09-30 | 로드맵 1·1b 구현 후, 같은 조건 | **79 passed** |
| 2026-09-30 | 로드맵 2·3 구현 후, 같은 조건 + grpcio/grpcio-tools/grpcio-health-checking/protobuf | **104 passed** |
| 2026-09-30 | 로드맵 4·5 + 프로파일링 모듈 구현 후, + psutil/nvidia-ml-py | **133 passed** |
| 2026-09-30 | 로드맵 6·6b(루프 연결) + 루프 스모크 테스트 후 | **142 passed** |
| 2026-09-30 | 로드맵 7·8 + analyze_run 후, + pandas/matplotlib | **149 passed** |
| 2026-09-30 | 로드맵 9·10(도구) 후 | **153 passed** |

## 변경 표

| 날짜 | 기능 | 파일 | 변경 내용 | 이유 / 근거 | 로드맵 |
|---|---|---|---|---|---|
| 2026-09-30 | 저장소 시작 | (전체) | `upstream/main`(`e6372ea`) 히스토리를 그대로 가져와 브랜치 시작. 서브모듈 gitlink 4개 유지, 초기화하지 않음 | [ADR 0004](adr/0004-upstream-import-preserve-history.md) | 0 |
| 2026-09-30 | 문서 | `docs/architecture-analysis.md` | 현재(단일 호스트) 구조 분석: 배포·모듈 의존·시퀀스·데이터 크기·환경·타이밍·UI 현황 | 분리 설계의 근거 | 1 |
| 2026-09-30 | 문서 | `docs/distributed-architecture.md` | 분리 후 토폴로지, 인스턴스 간 데이터 교환 명세, 시퀀스, pygame UI 방안, 전/후 비교, proto 초안, 리스크 | [ADR 0001~0003, 0005, 0006](adr/README.md) | 1 |
| 2026-09-30 | 문서 | `docs/adr/*.md` | 설계 결정 6건과 색인·템플릿 | 결정 이유와 탈락 후보 기록 요청 | 1 |
| 2026-09-30 | 문서 | `docs/distributed-roadmap.md` | 분리 구현 10단계, 파일·함수 단위 변경 목록 | 후속 구현 지침 | 1 |
| 2026-09-30 | 문서 | `docs/cheatsheet.md` | 인스턴스별 명령어 표 (구현 전 항목은 로드맵 단계 표시) | 운영 편의 | 1 |
| 2026-09-30 | 문서 | `docs/alpamayo15-notebooks-guide.md` | 공식 노트북 4개의 내용·준비물·g6e.xlarge 실행 가능성·예상 결과 | 모델 기능 사전 확인 | 1 |
| 2026-09-30 | 문서 | `docs/diagrams/*.svg` | 위 문서의 Mermaid 다이어그램을 SVG로 렌더링(mermaid-cli) | Mermaid 미지원 뷰어 대비 | 1 |
| 2026-09-30 | 문서 | `README.md` | 저장소 목적, 문서 색인, 업스트림 동기화 절 추가 | | 1 |
| 2026-09-30 | 문서(2차) | `docs/diagrams/README.md` | 다이어그램 11개 각각의 출처·의미·읽는 법 | 다이어그램 설명 요청 | 1 |
| 2026-09-30 | 문서(2차) | `docs/cheatsheet.md`, `docs/distributed-architecture.md`, `docs/distributed-roadmap.md`, `docs/adr/0005`, `docs/architecture-analysis.md` | "무엇이 어디서 도는가" 표와 세 모드 용어표 추가, `carlamayo.py`가 A에서 도는 이유 명시, S3 명령을 `rsync`/`scp`로 교체, 배포·open-loop 다이어그램 갱신 | 치트시트 혼동 해소, SSH 기반 운영에 맞춤 | 1 |
| 2026-09-30 | 문서(3차) | `docs/distributed-roadmap.md`, `docs/distributed-architecture.md` §9, `docs/adr/0007`, `docs/cheatsheet.md` | 실행 결과 폴더(`runs/<run_id>/`) 규칙과 run_id RPC 전달, 프로파일링(A/B 기록 항목, `tools/analyze_run.py`) 설계를 로드맵 1b·6b로 추가. 치트시트에 systemd 설명과 "B는 서버만 켜 두면 됨" 설명 | 재실행 시 덮어쓰기 방지, 보고서용 성능 기록 요청 | 1 |
| 2026-09-30 | torch 디커플링 | `module/inference.py` | 최상단 `import torch` 제거(linalg 설정 안에서 지연 import). `extract_trajectory_samples`가 numpy 입력도 받음 | A(sim host)에 torch 없이 루프 실행. 원격 어댑터는 numpy를 반환 | 1 |
| 2026-09-30 | torch 디커플링 | `module/visualization.py` | `import torch` 제거, `isinstance(..., torch.Tensor)`를 `hasattr(x, "detach")`로 | 같음 | 1 |
| 2026-09-30 | torch 디커플링 | `module/adapters/base.py` | `is_remote`, `quantization`, `oom_free` 속성, `runtime_summary()`(VRAM 문자열, torch 없으면 빈 문자열), `seed_everything()`, `run_inference/run_vqa(seed=)` 인자 | 루프가 torch를 직접 부르지 않고 어댑터에 위임. 시드는 open-loop 재현·parity용 | 1 |
| 2026-09-30 | torch 디커플링 | `module/adapters/alpamayo_{r1,1_5,2}.py` | `seed=` 인자 받아 샘플링 전 `seed_everything`, `load_model`에서 `quantization/oom_free` 기록 | 같음 | 1 |
| 2026-09-30 | torch 디커플링 | `module/loops/{closed_loop,live_open_loop,open_loop}.py` | `import torch` 제거. VRAM 출력 → `adapter.runtime_summary()`. open-loop의 `torch.cuda.manual_seed_all(42)` → `run_inference(seed=cfg.OPEN_LOOP_SEED)` | 같음 | 1 |
| 2026-09-30 | torch 디커플링 | `module/config.py` | `OPEN_LOOP_SEED = 42` | 시드 상수화 | 1 |
| 2026-09-30 | torch 디커플링 | `tests/test_torch_free_imports.py`(신규), `tests/test_inference_utils.py` | `sys.modules["torch"]=None`으로 torch 없는 환경을 흉내 내 A 쪽 모듈 14개가 import되는지 검사. numpy 입력 케이스 | 회귀 방지 | 1 |
| 2026-09-30 | 실행 결과 폴더 | `module/run_dir.py`(신규) | `build_run_id`, `RunDir.create/path/write_args/start_log/close`, `TeeStdout`, `resolve_output_video`. 폴더명 `<YYYYMMDD-HHMMSS>_<loop>_v<version>[_<mode>][_<tag>]`, 중복 시 `-2` | 재실행 시 덮어쓰기 방지, [ADR 0007](adr/0007-run-dir-and-run-id.md) | 1b |
| 2026-09-30 | 실행 결과 폴더 | `carlamayo.py` | `--runs-root`, `--run-tag`, `--no-run-dir` 플래그. `main()`이 폴더 생성 → `log.txt` 시작 → `args.json` 기록 → `args.run_dir` 전달 → 종료 시 닫기. 첫 줄에 `Run folder: ... (run_id=...)` 출력 | 같음 | 1b |
| 2026-09-30 | 실행 결과 폴더 | `module/loops/{closed_loop,live_open_loop,open_loop}.py` | `output_video`를 `resolve_output_video(args, cfg.*_OUTPUT_VIDEO)`로. run 폴더가 없으면(직접 `run()` 호출) 업스트림과 동일하게 현재 디렉터리 | 영상이 run 폴더에 저장 | 1b |
| 2026-09-30 | 실행 결과 폴더 | `.gitignore`, `tests/test_run_dir.py`(신규), `tests/test_carlamayo_launcher.py` | `runs/` 무시. 폴더명·유일성·args.json·로그·경로 해석 테스트, 런처가 run 폴더를 만들어 루프에 넘기는지 테스트 | | 1b |
| 2026-09-30 | RPC 계약 | `module/remote/alpamayo_inference.proto`(신규), `module/remote/alpamayo_inference_pb2*.py`(생성), `tools/gen_proto.sh` | `GetModelInfo`/`Predict`/`AnswerQuestion` 서비스, `ModelInfo`·`ImageStack`·`Tensor`·`ClientMeta(run_id 포함)`·`Timings` 메시지 | 두 호스트 간 계약, [ADR 0002](adr/0002-rpc-transport-grpc.md) | 2 |
| 2026-09-30 | RPC 계약 | `module/remote/codec.py`(신규), `tests/test_remote_codec.py` | 이미지 스택 JPEG/raw 인코딩·디코딩(RGB 유지), Tensor 직렬화, PSNR. torch 비의존 | [ADR 0003](adr/0003-image-encoding-jpeg-default.md) | 2 |
| 2026-09-30 | 추론 서버 | `module/remote/fake_adapter.py`(신규) | 입력의 결정적 함수로 궤적을 돌려주는 torch-free 어댑터(테스트·드라이런용, `sleep_sec`/`fail_with` 옵션) | GPU 없이 RPC 경로 검증 | 3 |
| 2026-09-30 | 추론 서버 | `module/remote/server.py`(신규), `tests/test_remote_server.py` | `AlpamayoServicer`(디코드 → `prepare_model_input` → `run_inference`/`run_vqa`, 모델 lock, 미워밍업 `FAILED_PRECONDITION`, 동시 요청 `RESOURCE_EXHAUSTED`, 잘못된 페이로드 `INVALID_ARGUMENT`, cuSOLVER→MAGMA 재시도, run_id별 `runs/<run_id>/server_info.json`, `on_request` 훅), `create_server`(헬스 서비스, 512 MB 메시지, keepalive), `build_model_info` | 서버 핵심. `closed_loop.py:244-256`의 linalg 재시도 로직을 서버로 이동 | 3 |
| 2026-09-30 | 원격 어댑터 | `module/adapters/__init__.py` | `VERSION_ALIASES`, `normalize_version()` 노출(torch 없이 버전 별칭 정규화) | 클라이언트 버전 검증·폴더명에 재사용 | 4 |
| 2026-09-30 | 원격 어댑터 | `module/remote/client.py`(신규), `tests/test_remote_client.py` | `RemoteAlpamayoAdapter`: `load_model()`=접속+`GetModelInfo` 핸드셰이크(버전·프로토콜·`NUM_FRAMES/NUM_HISTORY/IMG_*/NUM_TRAJ_SAMPLES` 검증, 리그·capability 복사, 워밍업 대기), `prepare_model_input()`=JPEG/raw 인코딩(워커 스레드에서), `run_inference/run_vqa`=RPC 호출·numpy 반환, `RemoteInferenceError`, 오류 후 재핸드셰이크, `on_rpc` 프로파일 훅 | 루프 코드 변경 없이 모델을 원격으로, [ADR 0001](adr/0001-topology-client-on-sim-host.md) | 4 |
| 2026-09-30 | 원격 어댑터 | `carlamayo.py` | `--inference-server`, `--image-encoding`, `--jpeg-quality`, `--rpc-timeout-sec`, `--rpc-connect-timeout-sec`; `build_adapter()`(원격이면 `RemoteAlpamayoAdapter`, 서버 전용 플래그 `--quantization/--oom-free*/--device-map` 거부); run 폴더명은 `normalize_version`으로(원격일 때 torch 어댑터 미import) | | 4 |
| 2026-09-30 | 원격 어댑터 | `module/loops/{closed_loop,live_open_loop,open_loop}.py` | `adapter.is_remote`면 CUDA linalg 설정·모델 옵션 출력 생략, `load_model()`만 호출. open-loop는 핸드셰이크 후 카메라 순서 계산(리그가 서버에서 오므로). 원격일 때 `model_data["meta"]`에 frame·revision 전달 | | 4 |
| 2026-09-30 | 추론 서버 | `alpamayo_server.py`(신규), `tests/test_alpamayo_server_cli.py` | CLI(`--version`/`--fake`, `--host/--port`, 모델 옵션, `--no-warmup`, `--runs-root`, `--profile`), 로드 → 서버 기동(NOT_SERVING) → 더미 워밍업 → SERVING, SIGINT/SIGTERM 종료 | B에서 실행하는 유일한 프로세스 | 5 |
| 2026-09-30 | 프로파일링 | `module/profiling.py`(신규), `tests/test_profiling.py` | `CsvRecorder`(백그라운드 스레드 CSV), `gpu_stats`(pynvml), `SystemSampler`(psutil CPU/RAM/네트워크 + GPU), `ClientProfiler`(tick/rpc/sys CSV), `ServerProfiler`(run_id별 `profile_server*.csv`) | 로드맵 6b 기반. 루프 연결은 다음 단계 | 6b |
| 2026-09-30 | 안전장치 | `module/config.py`, `module/loops/_common.py`, `module/loops/closed_loop.py`, `carlamayo.py` | `TRAJECTORY_MAX_AGE_SEC=6.0`, `trajectory_is_stale()`, `--trajectory-max-age-sec`. closed-loop가 PID 적용 직전 궤적 나이를 검사해 초과 시 궤적을 버리고 정지 | 서버 장애·타임아웃 후 옛 궤적으로 계속 주행하는 것 방지 | 6 |
| 2026-09-30 | 프로파일링 | `module/loops/_common.py`, `module/loops/{closed_loop,live_open_loop,open_loop}.py`, `carlamayo.py` | `start_client_profiler`(run 폴더에 `profile_client*.csv`, 원격 어댑터의 `on_rpc` 연결), `record_local_inference`(로컬 어댑터 추론 시간도 같은 CSV에), tick마다 `profiler.tick(...)`(tick/캡처/추론/제어/UI 시간, 속도·조향·궤적 나이). `--profile/--no-profile`, `--profile-interval-sec`. open-loop는 `predictions.npz`도 저장(parity용) | 보고서용 성능 기록 | 6b |
| 2026-09-30 | 버그 수정 | `module/loops/{closed_loop,live_open_loop}.py` | `viz_slot`/`num_cameras`를 `load_model()` 이후에 읽도록 이동(원격 어댑터는 핸드셰이크 전에는 리그가 비어 있음) | 스모크 테스트가 발견 | 4 |
| 2026-09-30 | 테스트 | `tests/test_loops_smoke.py`, `tests/test_loop_common.py` | 가짜 `carla` 모듈·가짜 `CARLAInterface`·가짜 PID로 closed-loop(sync/async)·live-open을 원격 어댑터 + 가짜 서버에 붙여 끝까지 실행. 제어 적용, run 폴더·CSV·서버 미러 폴더 확인, stale 가드 정지 확인 | GPU·CARLA 없이 루프 경로 회귀 방지 | 6b |
| 2026-09-30 | pygame UI | `carlamayo.py`, `module/loops/_common.py`, `module/loops/closed_loop.py` | `--pygame-ui` 기본 ON + `--no-pygame-ui`; `--start-paused/--no-start-paused`; `should_start_paused()`: navigation/vqa 모드에서 초기 프롬프트가 없을 때만 정지 시작, normal은 즉시 주행 | 모든 모드에서 주행 화면, 불필요한 시작 정지 제거, [ADR 0006](adr/0006-pygame-ui-on-sim-host.md) | 7 |
| 2026-09-30 | pygame UI | `module/loops/live_open_loop.py`, `module/pygame_ui.py` | live-open에 같은 카메라 창 추가(`mode="live-open"` 패널, Ctrl+P 정지, Esc 종료, `*_pygame_ui.mp4` 기록) | 오토파일럿 주행 관찰 | 7 |
| 2026-09-30 | 버그 수정 | `module/loops/{closed_loop,live_open_loop}.py` | `_check_capabilities`를 원격일 때는 핸드셰이크 뒤에 실행(capability가 서버에서 오므로). 스모크 테스트가 발견 | | 4 |
| 2026-09-30 | 문서 | `docs/navigation-mode.md`, `docs/vqa-mode.md`, `docs/inference-workflows.md` | "starts paused" 설명을 새 동작으로 갱신 | | 7 |
| 2026-09-30 | 환경 분리 | `requirements-sim.txt`(신규), `requirements-inference.txt`(신규), `requirements-carla.txt`·`requirements-alpamayo.txt`(호환용 `-r`), `pyproject.toml`(grpcio·protobuf·psutil·nvidia-ml-py, dev에 grpcio-tools), `.github/workflows/ci.yml`(의존성 추가, 스텁 최신 검사), `docs/environment-setup.md` §3 | 호스트별 설치 프로파일 | 8 |
| 2026-09-30 | 프로파일링 | `tools/analyze_run.py`(신규), `tools/fetch_server_profile.sh`(신규), `tests/test_analyze_run.py` | `summary.md`(run·server 정보, headline, 파일별 count/mean/std/min/p50/p95/max, status 집계)와 `plots/`(inference_time, rtt, server_breakdown, gpu_mem, cpu, net, trajectory_age, speed), `compare` 서브커맨드. B의 CSV를 rsync로 가져오는 스크립트 | 보고서용 산출물 | 6b |
| 2026-09-30 | 버그 수정 | `module/profiling.py` | CSV float 포맷을 `%.6g`에서 소수 6자리 고정으로(epoch 시각이 한 값으로 뭉개지던 문제, 플롯 검토 중 발견) | | 6b |
| 2026-09-30 | 배포 자산 | `deploy/aws/README.md`, `deploy/systemd/alpamayo-server.service`, `deploy/scripts/{setup-sim-host,setup-inference-host,sync-dataset-to-inference-host}.sh` | 인스턴스·보안그룹 표, systemd 유닛, 호스트별 설치 스크립트, 데이터셋 rsync, `--fake` 서버로 네트워크 경로 검증 절차 | 운영 | 9 |
| 2026-09-30 | parity | `tools/compare_predictions.py`(신규), `tests/test_compare_predictions.py` | 두 run의 `predictions.npz`를 프레임별로 비교해 `parity.md` 작성, `--atol` 초과 시 비정상 종료 | 로컬 vs 원격, raw vs JPEG 검증 | 10 |
| 2026-09-30 | 문서 | `docs/cheatsheet.md` | 구현된 명령으로 확정("(로드맵 N)" 표시 제거), 설치 스크립트·parity·프로파일 분석·문제 해결 항목 추가 | | 9 |
| 2026-09-30 | 버그 수정 | `deploy/scripts/setup-inference-host.sh`, `docs/environment-setup.md` | uv 파이썬에는 `ensurepip`/`pip`이 없어 스크립트가 중단되던 문제 → `uv pip install`로 교체, 설치 후 import 확인 추가. 실제 B 인스턴스에서 발견 | | 9 |
| 2026-09-30 | 문서 | `docs/cheatsheet.md`, `deploy/aws/README.md` | A→B 접속 준비를 "보안그룹(두 방법, 인바운드/아웃바운드 설명, 권한 요청 문구)" + "기존 키페어 pem으로 SSH config" 절차로 갱신. 실제 인스턴스에서 A→B가 멈추던(hang) 원인이 B의 launch-wizard 그룹임을 확인 | 운영 중 발견 | 9 |
| 2026-09-30 | 문서 | `docs/validation-checklist.md`(신규) | 실제 두 인스턴스 검증 절차 8단계(준비 → 가짜 서버 → 모델 서버 → 데이터 수집 → 원격 open-loop → parity → closed-loop 4모드·재시작 내성 → live-open → 결과 정리)를 명령·통과 기준·기록 항목·진행 상태로 정리 | 로드맵 10단계 진행 추적 | 10 |

| 2026-09-30 | 문서 정리 | `docs/distributed/`(이동) | 이 포크에서 추가한 문서·ADR·다이어그램을 `docs/distributed/`로 옮겨 업스트림 원본(`docs/*.md`)과 구분. 링크 전부 갱신 | 업스트림 문서와 한눈에 구분, 동기화 시 충돌 방지 | - |

> 위 변경 후 `python -m pytest -q tests`: **153 passed**.
