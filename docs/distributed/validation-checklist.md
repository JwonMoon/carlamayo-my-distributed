# 분리 환경 검증 체크리스트 (로드맵 10단계)

실제 두 인스턴스(A: g5.2xlarge `172.31.38.219`, B: g6e.xlarge `172.31.20.213`)에서 코드가
동작하는지 **순서대로** 확인하는 절차다. 앞 단계가 통과해야 뒤 단계가 의미 있다. 각 단계의
체크박스와 "기록" 칸을 진행하면서 채우고, 막히면 그 단계의 터미널 출력과
`runs/<run_id>/log.txt`를 공유한다. 명령의 상세는 [cheatsheet.md](cheatsheet.md).

상태 표기: ☐ 미완, ◐ 진행 중, ☑ 통과, ✗ 실패(사유 기록)

---

## 0. 두 인스턴스 준비

| 상태 | 항목 | 어디 | 명령 / 확인 | 통과 기준 |
|---|---|---|---|---|
| ☑ | 저장소 클론 + 브랜치 | A, B | `git clone ... ~/carlamayo && git checkout claude/nice-planck-dec7fo` | 두 곳 모두 같은 커밋 (`git log -1`) |
| ☑ | A 셋업 | A | `deploy/scripts/setup-sim-host.sh` → `source ~/.bashrc` | `ls ~/carla/CarlaUE4.sh`, `echo $CARLA_ROOT`, `source venv-sim/bin/activate && python -c "import carla, grpc, cv2, pygame"` |
| ☑ | B 셋업 | B | `deploy/scripts/setup-inference-host.sh` | `python -c "import alpamayo1_5, grpc, cv2, bitsandbytes"` → 오류 없음 (2026-09-30 확인: `B deps OK`) |
| ☐ | HF 로그인 | B | `hf auth login` | `hf auth whoami`에 계정 표시. 모델 게이트 승인 상태 |
| ☑ | 보안그룹 | AWS 콘솔 | B에 A의 그룹 추가 또는 22·50051 규칙 추가 (관리자 요청 → 2026-10-01 반영 확인) | A에서 `nc -zv 172.31.20.213 22` → `succeeded!` |
| ☑ | SSH A→B | A | `~/.ssh/config`에 pem 지정 후 `ssh ubuntu@172.31.20.213 hostname` | `ip-172-31-20-213` |

기록: A 셋업 성공, B 셋업은 `ensurepip` 버그로 중단 → 수동 `uv pip` 설치로 완료(스크립트는 `aa25b3d`에서 수정).

---

## 1. 가짜 서버로 네트워크·코드 경로 검증 (GPU·가중치 불필요)

| 상태 | 항목 | 어디 | 명령 | 통과 기준 |
|---|---|---|---|---|
| ☑ | 가짜 서버 기동 | B | `source a_venv/bin/activate && python alpamayo_server.py --fake --host 172.31.20.213 --port 50051` | 마지막 줄 `SERVING Fake Alpamayo ... warmed_up=True` |
| ☑ | 포트 | A | `nc -zv 172.31.20.213 50051` | `succeeded!` |
| ☑ | 왕복 | A | [deploy/aws/README.md](../../deploy/aws/README.md)의 스니펫 | `OK (1, 1, 1, 64, 3) rtt=... request=...MB` |

기록할 것: `rtt`(초), `request`(MB). 1080p JPEG 16장이면 5~8 MB, VPC 내부 왕복은 0.1~0.3 s 예상.

기록(2026-10-01): `OK (1, 1, 1, 64, 3) rtt=0.177s request=0.5MB`. 검은 이미지라 요청이 작다(실제 영상은 5~8 MB).

실패 시 원인 후보: 보안그룹(멈춤), `--host` 바인드 IP 오타(refused), A의 grpcio 미설치(import 오류),
**B에서 서버를 안 띄움**(클라이언트가 `no inference server at ... after 30s`로 종료. 2026-10-01에 실제로 겪음 → B에서
`ss -ltnp | grep 50051`로 먼저 확인), A의 `https_proxy` 환경변수(gRPC가 프록시로 나감 → `export no_grpc_proxy=172.31.20.213`).

---

## 2. 실제 모델 서버 기동

| 상태 | 항목 | 어디 | 명령 | 통과 기준 |
|---|---|---|---|---|
| ☐ | 서버 기동 | B | `tmux new -s server` 안에서 `python alpamayo_server.py --version 1.5 --host 172.31.20.213 --port 50051` | `SERVING Alpamayo 1.5 ... cameras=4`. 첫 실행은 22 GB 다운로드 + 로드 + 워밍업으로 수 분~수십 분 |
| ☐ | VRAM | B | `nvidia-smi` | 약 21~24 GB 사용 |

기록할 것: 로드 시간(로그의 `Model loaded in ...s`), 워밍업 시간, VRAM.

실패 시 원인 후보: HF 게이트 미승인(401/403), flash-attn 오류(→ SDPA 폴백 옵션 필요, 로그 공유), 디스크 부족(`df -h`).

---

## 3. 데이터 수집 (open-loop 입력 확보)

| 상태 | 항목 | 어디 | 명령 | 통과 기준 |
|---|---|---|---|---|
| ☐ | CARLA 서버 | A | `cd ~/carla && ./CarlaUE4.sh -RenderOffScreen -quality-level=Epic` (별도 터미널/tmux) | `nvidia-smi`에 CarlaUE4 약 6 GB |
| ☐ | 수집 | A | `python data_collect.py`, 1~2분 뒤 Ctrl+C | `carla_data/trajectory.json`과 `carla_data/camera_*/` 생성, 프레임 수 100 이상 |

기록할 것: 프레임 수(`python -c "import json; print(len(json.load(open('carla_data/trajectory.json'))))"`), 폴더 크기(`du -sh carla_data`).

---

## 4. open-loop로 원격 추론 첫 실행 (CARLA 불필요)

| 상태 | 항목 | 어디 | 명령 | 통과 기준 |
|---|---|---|---|---|
| ☐ | 원격 open-loop | A | `python carlamayo.py --loop open --version 1.5 --data-root carla_data --inference-server 172.31.20.213:50051 --run-tag remote-jpeg` | 프레임마다 `Inference: X.XXs` 출력, `runs/<run_id>/`에 mp4·`predictions.npz`·`profile_client*.csv` |
| ☐ | 서버 프로파일 회수 | A | `tools/fetch_server_profile.sh <run_id>` | `runs/<run_id>/profile_server.csv` 생김 |
| ☐ | 분석 | A | `python tools/analyze_run.py runs/<run_id>` | `summary.md`, `plots/*.png` 생성 |

기록할 것: `summary.md`의 headline(`rtt_mean_s`, `inference_mean_s`, `overhead_mean_s`, `request_mb`, `upload_mbps`).

---

## 5. parity 검사 (원격 경로가 결과를 바꾸지 않는지)

| 상태 | 항목 | 어디 | 명령 | 통과 기준 |
|---|---|---|---|---|
| ☐ | 데이터 복사 | A | `deploy/scripts/sync-dataset-to-inference-host.sh` | B의 `~/carlamayo/carla_data/` |
| ☐ | B 로컬 실행 | B | `python carlamayo.py --loop open --version 1.5 --data-root carla_data --run-tag local` | `runs/<run_local>/predictions.npz` |
| ☐ | A 원격 raw | A | 4단계 명령 + `--image-encoding raw_rgb8 --run-tag remote-raw` | `runs/<run_raw>/predictions.npz` |
| ☐ | 비교 | A | `rsync -avz ubuntu@172.31.20.213:~/carlamayo/runs/<run_local>/ runs/<run_local>/` → `python tools/compare_predictions.py runs/<run_local> runs/<run_raw>` | raw: `bitwise identical: True` 또는 max diff 1e-4 이하 |
| ☐ | JPEG 영향 | A | `python tools/compare_predictions.py runs/<run_local> runs/<run_remote_jpeg> --atol 1` | `parity.md`의 평균 xy 거리 기록 (보고서의 "JPEG 영향" 근거) |

기록할 것: raw의 max diff, JPEG의 평균 xy 거리(m)와 max diff.

---

## 6. closed-loop

DCV 세션 터미널에서 실행(또는 `export DISPLAY=:0`). 처음엔 2~3분만 돌리고 Esc.

| 상태 | 모드 | 어디 | 명령 | 통과 기준 |
|---|---|---|---|---|
| ☐ | normal | A | `python carlamayo.py --loop closed --version 1.5 --async --inference-server 172.31.20.213:50051 --run-tag normal` | 창이 뜨고 차량이 주행, 터미널에 `Inference done`·`Speed:` 반복, 충돌 시 리스폰 |
| ☐ | navigation | A | 위 + `--mode navigation --navigation-text "Turn right in 30m" --run-tag nav` | 정지 없이 시작, CoT에 지시 반영, 창에서 Enter로 지시 변경 시 즉시 적용 |
| ☐ | navigation + CFG | A | 위 + `--navigation-weight 1.5 --run-tag cfg15` | 서버 로그에 요청 처리, 추론 시간이 비CFG보다 김(CFG 경로) |
| ☐ | vqa | A | 위 + `--mode vqa --vqa-question "What is ahead?" --run-tag vqa` | 차량 정지, 패널·터미널에 답변 |
| ☐ | 서버 재시작 내성 | A+B | closed-loop 중 B 서버 Ctrl+C → 10 s 후 재기동 | A가 `Inference error` 출력 후 정지(궤적 나이 6 s), 서버 복귀 후 다시 주행 |
| ☐ | 분석 | A | `tools/fetch_server_profile.sh <run_id>` → `python tools/analyze_run.py runs/<run_id>`; `python tools/analyze_run.py compare runs/<normal> runs/<nav> runs/<cfg15> runs/<vqa>` | `summary.md`, `compare.md` |

기록할 것: `rtt_mean_s`, `overhead_mean_s`, `traj_age_p95_s`, `sim_realtime_ratio`, `server_gpu_peak_gb`, 모드별 비교표.

---

## 7. live-open-loop

| 상태 | 항목 | 어디 | 명령 | 통과 기준 |
|---|---|---|---|---|
| ☐ | live-open | A | `python carlamayo.py --loop live-open --version 1.5 --async --inference-server 172.31.20.213:50051 --run-tag live` | 오토파일럿 주행, 창에 예측 궤적 오버레이, 영상 2개 생성 |

---

## 8. 결과 정리

| 상태 | 항목 | 내용 |
|---|---|---|
| ☐ | 결과 회수 | 로컬 PC: `scp -r ubuntu@<A>:~/carlamayo/runs/<run_id> ./results/` |
| ☐ | 문서 반영 | 각 단계의 기록값을 [distributed-architecture.md](distributed-architecture.md) "실측" 절과 [changes-from-upstream.md](changes-from-upstream.md) 검증 기록에 추가, 로드맵 10단계 ☑ |

---

## 알려진 주의점

- B의 `uv sync`가 flash-attn 빌드에 실패하면 SDPA 폴백이 필요하다. 2026-09-30 B 셋업에서는 flash-attn 2.8.3이 정상 설치됐다.
- 가짜 서버는 버전 `fake`를 광고하므로 `carlamayo.py --version 1.5`로는 붙지 않는다(의도된 가드). 1단계는 스니펫으로 검증한다.
- A→B가 "refused"가 아니라 멈추면 보안그룹, refused면 서버 미기동 또는 `--host` 오타다.
