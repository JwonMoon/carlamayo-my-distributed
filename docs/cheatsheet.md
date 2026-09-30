# 인스턴스별 명령어 치트시트

## 0. 무엇이 어디서 도는가

| 기호 | 인스턴스 | 내부 IP | 여기서 실행하는 것 |
|---|---|---|---|
| **[A]** | g5.2xlarge | `172.31.38.219` | CARLA 서버, **`carlamayo.py`(open/closed/live-open 전부)**, `data_collect.py`, pygame UI(DCV), 프로파일 분석 |
| **[B]** | g6e.xlarge | `172.31.20.213` | **`alpamayo_server.py`**(모델을 한 번 로드해 gRPC로 상주), 공식 노트북 |

`carlamayo.py`는 CARLA와 **같은 인스턴스(A)** 에서 돈다. 이 프로그램이 CARLA로부터 매 tick
카메라 4장(초당 300 MB 이상)을 받고 NPC 교통을 관리하기 때문에 CARLA 옆에 있어야 한다.
모델만 B에 두고, `carlamayo.py`는 `--inference-server 172.31.20.213:50051` 옵션으로 1초에 한 번
압축 이미지(5~8 MB)를 B에 보내 궤적을 받아 온다. "A는 CARLA만, B에서 `carlamayo.py`" 구성은
업스트림의 `--carla-host` 플래그로 가능하지만 위 트래픽이 네트워크를 건너야 해서 택하지
않았다([ADR 0001](adr/0001-topology-client-on-sim-host.md)).

두 인스턴스 모두 SSH로 접속하고, 저장소를 `~/carlamayo`에 클론해 그 안에서 명령을 실행한다.
아래 명령은 전부 그 터미널에서 그대로 치는 것이다. SSH 사용자명은 AMI에 따라 `ubuntu` 또는
`ec2-user`이므로 예시의 `ubuntu`를 맞게 바꾼다.

### 용어: 세 가지 실행 모드

| `--loop` | 시뮬레이터 | 운전 주체 | 모델 출력의 용도 | 언제 쓰나 |
|---|---|---|---|---|
| `open` | 없음. 녹화된 `carla_data/`를 재생 | 없음 | 영상에 그림 | 모델 단독 평가, RPC 검증 |
| `live-open` | 실시간 CARLA | **CARLA 오토파일럿** | 영상에 오버레이만, 핸들에 닿지 않음 | 실제 주행 정책과 모델 예측을 나란히 관찰 |
| `closed` | 실시간 CARLA | **모델**(PID 경유) | 조향·가속·제동으로 적용 | 본 실험 |

### 모든 실행의 공통 산출물

실행할 때마다 `~/carlamayo/runs/<run_id>/` 폴더가 생기고(`<run_id>` = `시각_loop_v버전[_모드][_태그]`,
터미널 첫 줄에 출력), 그 안에 영상, `args.json`, `log.txt`, `profile_client*.csv`가 쌓인다.
`--run-tag 이름`으로 꼬리표를 붙이고, `--no-profile`로 프로파일링을 끄고, `--no-run-dir`로
업스트림처럼 현재 폴더에 저장할 수 있다.

---

처음 세팅한 뒤 무엇을 어떤 순서로 확인할지는 [validation-checklist.md](validation-checklist.md)에 있다.

## 1. 최초 세팅

### [A] sim host

```bash
git clone https://github.com/jwonmoon/carlamayo-my-distributed.git ~/carlamayo
~/carlamayo/deploy/scripts/setup-sim-host.sh      # CARLA 0.9.16, venv-sim(torch 없음), ffmpeg, Vulkan
source ~/.bashrc                                   # CARLA_ROOT 반영
```

수동으로 하려면 [deploy/aws/README.md](../deploy/aws/README.md)와 [environment-setup.md](environment-setup.md) §1, §3.

### [B] inference host

```bash
git clone https://github.com/jwonmoon/carlamayo-my-distributed.git ~/carlamayo
~/carlamayo/deploy/scripts/setup-inference-host.sh   # uv env, alpamayo1.5 서브모듈, gRPC 의존성
source ~/carlamayo/a_venv/bin/activate
hf auth login                                        # 모델 게이트 승인 후 (토큰은 B에만)
```

### A → B 접속 준비 (한 번만)

**1) 보안그룹: B가 A에서 오는 연결을 받도록 한다.** 인바운드 규칙은 "누가 이 인스턴스의 어느
포트로 들어와도 되는가"이고, 아웃바운드(나가는 쪽)는 기본값이 전부 허용이라 손댈 일이 없다.
A→B에 필요한 것은 **B의 인바운드**뿐이다. 둘 중 하나:

| 방법 | 어디서 | 내용 |
|---|---|---|
| 1 (간단) | EC2 → 인스턴스 → B → 작업 → 보안 → 보안 그룹 변경 | A가 쓰는 보안그룹(`vs-advancedsw-adas-ec2`, 내부망 전체 TCP 허용)을 B에 **추가** (기존 그룹 유지) |
| 2 (최소 개방) | EC2 → 보안 그룹 → B의 그룹 → 인바운드 규칙 편집 | TCP 22, TCP 50051 두 규칙 추가, 원본 = A의 보안그룹 ID |

권한 오류(`ec2:DescribeSecurityGroupRules ...`)가 나면 관리자에게 위 중 하나를 요청한다
([deploy/aws/README.md](../deploy/aws/README.md)에 요청 문구 예시).

**2) SSH 키: 기존 인스턴스 키페어(pem)를 그대로 쓴다.**

```bash
# [A]  pem을 A에 두고 config로 자동 사용
chmod 400 ~/.ssh/<키페어>.pem
cat >> ~/.ssh/config <<'EOF'
Host 172.31.20.213
    User ubuntu
    IdentityFile ~/.ssh/<키페어>.pem
EOF
chmod 600 ~/.ssh/config
# [A] 확인
nc -zv 172.31.20.213 22            # succeeded! (멈추면 1)의 보안그룹 문제)
ssh ubuntu@172.31.20.213 hostname  # ip-172-31-20-213
```

pem 없이 쓰려면 `ssh-copy-id -i ~/.ssh/id_ed25519.pub -o IdentityFile=~/.ssh/<키페어>.pem ubuntu@172.31.20.213`.

---

## 2. 서버·시뮬레이터 기동

| 순서 | 어디 | 명령 | 확인 |
|---|---|---|---|
| 1 | [B] | `cd ~/carlamayo && source a_venv/bin/activate && python alpamayo_server.py --version 1.5 --host 172.31.20.213 --port 50051` | 로그 마지막에 `SERVING ... warmed_up=True` |
| 1 (대안) | [B] | `sudo systemctl start alpamayo-server && journalctl -u alpamayo-server -f` (서비스 등록은 [deploy/aws/README.md](../deploy/aws/README.md)) | 같음 |
| 2 | [A] | `cd ~/carla && ./CarlaUE4.sh -RenderOffScreen -quality-level=Epic` | 별도 터미널(또는 `tmux`)에서 유지 |
| 3 | [A] | `nvidia-smi` | CARLA가 약 6 GB 사용 |

1과 "1 (대안)"은 **둘 중 하나**만 한다. `systemd`는 Linux의 백그라운드 서비스 관리자로, 서비스로
등록하면 터미널을 닫아도 서버가 유지되고 재부팅·크래시 시 자동으로 다시 뜨며 로그는
`journalctl`로 본다. 직접 실행할 때는 `tmux` 안에서 실행해 SSH가 끊겨도 유지되게 한다:

```bash
# [B]
tmux new -s server            # 세션 열기
cd ~/carlamayo && source a_venv/bin/activate && python alpamayo_server.py --version 1.5 --host 172.31.20.213 --port 50051
# Ctrl+B, D 로 빠져나오기 / 다시 보려면 tmux attach -t server
```

**B에서 할 일은 이것뿐이다.** 아래 §4~6의 open/closed/live-open, navigation, CFG, VQA 어느 것을
A에서 실행하든 B의 명령은 바뀌지 않는다. 프롬프트·가중치·질문은 A가 보내는 요청에 실려 간다.
B에서 바꿀 일이 있는 것은 모델 로딩 옵션(`--version`, `--quantization`, `--oom-free`)뿐이며,
그때만 서버를 재시작한다.

### 모델 없이 네트워크 경로만 먼저 확인하기

```bash
# [B]  GPU·가중치 없이 가짜 모델 서빙
python alpamayo_server.py --fake --host 172.31.20.213 --port 50051
# [A]
nc -zv 172.31.20.213 50051
```
왕복 검증 스니펫은 [deploy/aws/README.md](../deploy/aws/README.md) 참조.

---

## 3. 데이터 수집  [A 전용]

CARLA가 있는 A에서만 한다. B는 데이터를 만들지 않는다.

```bash
cd ~/carlamayo && source venv-sim/bin/activate
python data_collect.py                     # Ctrl+C로 종료 → ~/carlamayo/carla_data/ 생성
```

B에서 open-loop(아래 §4 경로 1)를 돌리려면 그 데이터를 B로 복사한다.

```bash
# [A]
deploy/scripts/sync-dataset-to-inference-host.sh          # rsync → ubuntu@172.31.20.213:~/carlamayo/carla_data/
```

---

## 4. open-loop

| 경로 | 어디 | 명령 |
|---|---|---|
| 경로 1: B 로컬(기본) | [B] | `cd ~/carlamayo && source a_venv/bin/activate && python carlamayo.py --loop open --version 1.5 --data-root carla_data` |
| 경로 2: A 원격(RPC 검증) | [A] | `python carlamayo.py --loop open --version 1.5 --data-root carla_data --inference-server 172.31.20.213:50051` |
| 경로 2, 무압축 | [A] | 위 명령에 `--image-encoding raw_rgb8` |

출력: 실행한 인스턴스의 `~/carlamayo/runs/<run_id>/carla_alpamayo_open_loop_result.mp4`, `predictions.npz`

### parity 검사 (경로 1과 경로 2가 같은 궤적을 내는지)

```bash
# [B] 경로 1 실행 → runs/<run_local>  ;  [A] 경로 2 실행(raw) → runs/<run_remote>
# [A] B의 예측을 가져와 비교
rsync -avz ubuntu@172.31.20.213:~/carlamayo/runs/<run_local>/ runs/<run_local>/
python tools/compare_predictions.py runs/<run_local> runs/<run_remote>          # raw: 거의 0 기대
python tools/compare_predictions.py runs/<run_local> runs/<run_remote_jpeg> --atol 1   # JPEG: 차이 측정
```

---

## 5. closed-loop  [A]

DCV 세션 안의 터미널에서 실행한다. SSH 터미널에서 실행하려면 먼저 `export DISPLAY=:0`.
pygame 창은 기본으로 켜진다(`--no-pygame-ui`로 끔).

```bash
cd ~/carlamayo && source venv-sim/bin/activate && export CARLA_ROOT=~/carla
```

| 모드 | 명령 |
|---|---|
| normal | `python carlamayo.py --loop closed --version 1.5 --async --inference-server 172.31.20.213:50051` |
| normal, 창 없이 | 위 + `--no-pygame-ui` |
| navigation, 초기 지시 | 위 + `--mode navigation --navigation-text "Turn right in 30m"` (바로 주행 시작) |
| navigation, 창에서 첫 지시 입력 | 위 + `--mode navigation` (정지 상태로 시작, 입력 후 Ctrl+P) |
| navigation + CFG | 위 + `--mode navigation --navigation-text "Turn right in 30m" --navigation-weight 1.5` (창 입력창에는 `텍스트 \| 1.5`) |
| vqa | 위 + `--mode vqa --vqa-question "What is ahead?"` (차량은 정지, 답은 패널·터미널) |
| 강제로 정지 상태에서 시작 / 절대 정지 안 함 | 위 + `--start-paused` / `--no-start-paused` |
| 결과 폴더 꼬리표 | 위 + `--run-tag cfg15` |
| 오래된 궤적 정지 기준 바꾸기 | 위 + `--trajectory-max-age-sec 8` (기본 6, 0이면 끔) |
| 요청 타임아웃 | 위 + `--rpc-timeout-sec 60` (기본 120) |

UI 조작: `Enter` 프롬프트 적용, `Ctrl+P` 일시정지/재개(시뮬 세계 전체 정지), `Esc` 종료.
출력: `~/carlamayo/runs/<run_id>/` 안에 영상 2개(`*_result.mp4`, `*_pygame_ui.mp4`), `args.json`,
`log.txt`, `profile_client*.csv`

업스트림처럼 A 한 대에서 모델까지 돌리려면 `--inference-server`를 빼고 A에 모델 환경을 갖춘다
([environment-setup.md §3.1](environment-setup.md)). A의 24 GB로는 1.5가 빠듯하므로 `--quantization` 권장.

---

## 6. live-open-loop  [A]

오토파일럿이 운전하고 모델은 관찰만 한다(§0 용어 표). 같은 pygame 창이 뜬다.

```bash
python carlamayo.py --loop live-open --version 1.5 --async --inference-server 172.31.20.213:50051
```
출력: `~/carlamayo/runs/<run_id>/carla_alpamayo_live_open_loop_result.mp4`, `..._pygame_ui.mp4`

---

## 7. 프로파일 분석

실행이 끝나면 A에서 B의 서버 기록을 같은 이름의 폴더로 가져와 분석한다. `<run_id>`는 실행 시
터미널 첫 줄에 출력된다(`ls -t runs | head -1`로도 확인).

```bash
# [A]
cd ~/carlamayo && source venv-sim/bin/activate
tools/fetch_server_profile.sh <run_id>            # B의 profile_server*.csv → runs/<run_id>/
python tools/analyze_run.py runs/<run_id>         # → runs/<run_id>/summary.md, plots/*.png
python tools/analyze_run.py compare runs/<id1> runs/<id2>   # 여러 실행 비교표 → compare.md
```

`summary.md`에는 실행 정보, headline(왕복 시간·추론 시간·오버헤드·요청 크기·업로드 대역폭·
실시간 비율·궤적 나이 등), 파일별 count/mean/std/min/p50/p95/max 표, 그래프 링크가 들어간다.
B에서 open-loop를 로컬로 돌린 경우(§4 경로 1)는 B에서 바로 `python tools/analyze_run.py runs/<run_id>`.

---

## 8. 결과 가져오기

로컬 PC에서 실행한다. `<A>`/`<B>`는 SSH로 접속할 때 쓰는 주소(공인 IP 또는 호스트명)다.

```bash
scp -r ubuntu@<A>:~/carlamayo/runs/<run_id> ./results/     # closed, live-open, A 원격 open-loop
scp -r ubuntu@<B>:~/carlamayo/runs/<run_id> ./results/     # B 로컬 open-loop
```

---

## 9. 상태 확인·문제 해결

| 목적 | 어디 | 명령 |
|---|---|---|
| 서버 포트 열림 | [A] | `nc -zv 172.31.20.213 50051` |
| 서버 health | [A] | `python -c "import grpc; from grpc_health.v1 import health_pb2, health_pb2_grpc; print(health_pb2_grpc.HealthStub(grpc.insecure_channel('172.31.20.213:50051')).Check(health_pb2.HealthCheckRequest()))"` (`pip install grpcio-health-checking` 필요) |
| GPU | [A]/[B] | `nvidia-smi` |
| 서버 로그 | [B] | `journalctl -u alpamayo-server -f` (systemd) 또는 `tmux attach -t server` |
| CARLA 응답 | [A] | `python -c "import carla; c=carla.Client('localhost',2000); c.set_timeout(5); print(c.get_server_version())"` |
| pygame 창이 안 뜸 | [A] | DCV 세션 터미널에서 실행하거나 `export DISPLAY=:0`, 또는 `--no-pygame-ui` |
| `agents.navigation.controller` 없음 | [A] | `export CARLA_ROOT=~/carla` |
| "server serves Alpamayo '2' but --version '1.5'" | [A] | B의 서버 `--version`과 A의 `--version`을 맞춘다 |
| "NUM_FRAMES: client 4 != server ..." | [A] | 두 호스트의 `module/config.py`가 다르다. 같은 커밋으로 맞춘다 |
| 서버 재시작 중 클라이언트 | [A] | 오류 출력 후 다음 요청에서 자동 재접속. 궤적 나이 6 s 초과 시 정지 |
| gRPC 스텁 오류 | 양쪽 | `tools/gen_proto.sh` 후 커밋(CI가 검사) |

---

## 10. 종료

| 어디 | 명령 |
|---|---|
| [A] | 클라이언트 `Esc` 또는 Ctrl+C → CARLA 터미널 Ctrl+C |
| [B] | 서버 Ctrl+C 또는 `sudo systemctl stop alpamayo-server` |
| 비용 | 실험 없을 때 두 인스턴스 모두 stop. open-loop만 할 때는 A를 stop |

---

## 11. 공식 Alpamayo 1.5 노트북  [B]

[alpamayo15-notebooks-guide.md](alpamayo15-notebooks-guide.md) 참조.

```bash
# [B]
cd ~/carlamayo/third_party/alpamayo1.5/notebooks
source ~/carlamayo/a_venv/bin/activate
uv pip install mediapy ipykernel ipywidgets jupyter
jupyter notebook --no-browser --port 8888

# 로컬 PC
ssh -N -L 8888:localhost:8888 ubuntu@<B>      # 브라우저 http://localhost:8888
```
