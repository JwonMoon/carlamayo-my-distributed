# 인스턴스별 명령어 치트시트

## 0. 무엇이 어디서 도는가

| 기호 | 인스턴스 | 내부 IP | 여기서 실행하는 것 |
|---|---|---|---|
| **[A]** | g5.2xlarge | `172.31.38.219` | CARLA 서버, **`carlamayo.py`(open/closed/live-open 전부)**, `data_collect.py`, pygame UI(DCV) |
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

> "(로드맵 N)" 표시가 붙은 명령은 [distributed-roadmap.md](distributed-roadmap.md)의 해당 단계가
> 구현된 뒤에 동작한다. 표시가 없는 명령은 지금 업스트림 코드로도 동작한다.

---

## 1. 최초 세팅

### [A] sim host

```bash
# 저장소
git clone https://github.com/jwonmoon/carlamayo-my-distributed.git ~/carlamayo
cd ~/carlamayo

# CARLA 0.9.16
mkdir -p ~/carla && cd ~/carla
wget https://tiny.carla.org/carla-0-9-16-linux
tar -xvzf carla-0-9-16-linux
echo 'export CARLA_ROOT=~/carla' >> ~/.bashrc && source ~/.bashrc

# Python 환경 (torch 없음)
cd ~/carlamayo
python3.10 -m venv venv-sim
source venv-sim/bin/activate
pip install -r requirements-carla.txt          # (로드맵 8 이후: requirements-sim.txt)
sudo apt-get install -y ffmpeg
```

### [B] inference host

```bash
git clone https://github.com/jwonmoon/carlamayo-my-distributed.git ~/carlamayo
cd ~/carlamayo
git submodule update --init third_party/alpamayo1.5      # 1.5만
curl -LsSf https://astral.sh/uv/install.sh | sh && export PATH="$HOME/.local/bin:$PATH"
uv venv a_venv --python 3.12
source a_venv/bin/activate
uv sync --active
python -m ensurepip --upgrade
python -m pip install --no-deps -e third_party/alpamayo1.5
python -m pip install -r requirements-alpamayo.txt        # (로드맵 8 이후: requirements-inference.txt)
hf auth login                                             # 모델 게이트 승인 후
```

### A ↔ B 사이 파일 복사 준비 (한 번만)

A에서 B로 `rsync`/`scp`를 쓰려면 A의 SSH 키가 B에 등록되어 있어야 한다.

```bash
# [A]
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519      # 이미 있으면 생략
cat ~/.ssh/id_ed25519.pub                             # 출력 내용을 복사
# [B]
echo '<A의 공개키 한 줄>' >> ~/.ssh/authorized_keys
# [A] 확인
ssh ubuntu@172.31.20.213 hostname
```

---

## 2. 서버·시뮬레이터 기동

| 순서 | 어디 | 명령 | 확인 |
|---|---|---|---|
| 1 | [B] | `cd ~/carlamayo && source a_venv/bin/activate && python alpamayo_server.py --version 1.5 --host 172.31.20.213 --port 50051` (로드맵 5) | 로그에 `warmed_up=True`, `SERVING` |
| 1 (대안) | [B] | `sudo systemctl start alpamayo-server && journalctl -u alpamayo-server -f` (로드맵 9) | 같음 |
| 2 | [A] | `cd ~/carla && ./CarlaUE4.sh -RenderOffScreen -quality-level=Epic` | 별도 터미널(또는 `tmux`)에서 유지 |
| 3 | [A] | `nvidia-smi` | CARLA가 약 6 GB 사용 |

1과 "1 (대안)"은 **둘 중 하나**만 한다. `systemd`는 Linux의 백그라운드 서비스 관리자로, 서비스로
등록하면 터미널을 닫아도 서버가 유지되고 재부팅·크래시 시 자동으로 다시 뜨며 로그는
`journalctl`로 본다. 서비스 파일은 로드맵 9에서 만든다. 그 전에는 1번을 `tmux` 안에서 실행해
SSH가 끊겨도 유지되게 한다:

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
rsync -avz --progress ~/carlamayo/carla_data/ ubuntu@172.31.20.213:~/carlamayo/carla_data/
```

---

## 4. open-loop

| 경로 | 어디 | 명령 |
|---|---|---|
| 경로 1: B 로컬(기본, 지금 가능) | [B] | `cd ~/carlamayo && source a_venv/bin/activate && python carlamayo.py --loop open --version 1.5 --data-root carla_data` |
| 경로 2: A 원격(RPC 검증) | [A] | `python carlamayo.py --loop open --version 1.5 --data-root carla_data --inference-server 172.31.20.213:50051` (로드맵 4) |
| 경로 2, 무압축 | [A] | 위 명령에 `--image-encoding raw` |

출력: 실행한 인스턴스의 `~/carlamayo/runs/<run_id>/carla_alpamayo_open_loop_result.mp4` (로드맵 1b 이전에는 `~/carlamayo/` 바로 아래)

---

## 5. closed-loop  [A]

DCV 세션 안의 터미널에서 실행한다. SSH 터미널에서 실행하려면 먼저 `export DISPLAY=:0`.

```bash
cd ~/carlamayo && source venv-sim/bin/activate && export CARLA_ROOT=~/carla
```

| 모드 | 명령 |
|---|---|
| normal | `python carlamayo.py --loop closed --version 1.5 --async --inference-server 172.31.20.213:50051` (로드맵 4) |
| normal, UI 끔 | 위 + `--no-pygame-ui` (로드맵 7) |
| navigation, 초기 지시 | 위 + `--mode navigation --navigation-text "Turn right in 30m" --navigation-weight 1.0` |
| navigation + CFG | 위 + `--mode navigation --navigation-weight 1.5` (UI 입력창에 `텍스트 \| 1.5`) |
| vqa | 위 + `--mode vqa --vqa-question "What is ahead?"` (차량은 정지, 답은 패널·터미널) |
| 첫 프롬프트를 UI에서 받고 시작 | 위 + `--start-paused` (로드맵 7) |
| 결과 폴더 이름에 꼬리표 | 위 + `--run-tag cfg15` |
| 결과 폴더 없이 업스트림처럼 현재 폴더에 저장 | 위 + `--no-run-dir` |
| 프로파일링 끄기 | 위 + `--no-profile` (로드맵 6b, 기본은 켜짐) |

UI 조작: `Enter` 프롬프트 적용, `Ctrl+P` 일시정지/재개(시뮬 세계 전체 정지), `Esc` 종료.
출력: `~/carlamayo/runs/<run_id>/` 안에 영상 2개, `args.json`, `log.txt`, `profile_client*.csv` (로드맵 1b·6b 이전에는 `~/carlamayo/` 바로 아래 영상만)

분리 구현 전(지금)에 업스트림 그대로 돌려 보려면 A에 모델 환경까지 갖추고 `--inference-server`
없이 실행한다. A의 24 GB로는 1.5가 빠듯하므로 `--quantization`을 권한다.

---

## 6. live-open-loop  [A]

오토파일럿이 운전하고 모델은 관찰만 한다(§0 용어 표).

```bash
python carlamayo.py --loop live-open --version 1.5 --async --inference-server 172.31.20.213:50051   # (로드맵 4)
```
출력: `~/carlamayo/runs/<run_id>/carla_alpamayo_live_open_loop_result.mp4` (로드맵 1b 이전에는 `~/carlamayo/` 바로 아래)

---

## 7. 프로파일 분석 (로드맵 6b)

실행이 끝나면 A에서 B의 서버 기록을 같은 이름의 폴더로 가져와 분석한다. `<run_id>`는 실행 시
터미널 첫 줄에 출력되는 폴더명이다(`ls -t runs | head -1`로도 확인).

```bash
# [A]
cd ~/carlamayo
tools/fetch_server_profile.sh <run_id>            # B의 profile_server*.csv → runs/<run_id>/
python tools/analyze_run.py runs/<run_id>         # → runs/<run_id>/summary.md, plots/*.png
python tools/analyze_run.py compare runs/<id1> runs/<id2>   # 여러 실행 비교표
```

B에서 open-loop를 로컬로 돌린 경우(§4 경로 1)는 B에서 바로 `python tools/analyze_run.py runs/<run_id>`.

---

## 7b. 결과 가져오기

로컬 PC에서 실행한다. `<A>`/`<B>`는 SSH로 접속할 때 쓰는 주소(공인 IP 또는 호스트명)다.

```bash
scp -r ubuntu@<A>:~/carlamayo/runs/<run_id> ./results/     # closed, live-open, A 원격 open-loop
scp -r ubuntu@<B>:~/carlamayo/runs/<run_id> ./results/     # B 로컬 open-loop
# 로드맵 1b 이전(폴더 없음): scp ubuntu@<A>:~/carlamayo/carla_alpamayo_*_result*.mp4 ./results/
```

---

## 8. 상태 확인·문제 해결

| 목적 | 어디 | 명령 |
|---|---|---|
| 서버 포트 열림 | [A] | `nc -zv 172.31.20.213 50051` |
| 서버 health | [A] | `grpc_health_probe -addr=172.31.20.213:50051` (로드맵 5) |
| GPU | [A]/[B] | `nvidia-smi` |
| 서버 로그 | [B] | `journalctl -u alpamayo-server -f` (systemd 사용 시) |
| CARLA 응답 | [A] | `python -c "import carla; c=carla.Client('localhost',2000); c.set_timeout(5); print(c.get_server_version())"` |
| pygame 창이 안 뜸 | [A] | DCV 세션 터미널에서 실행하거나 `export DISPLAY=:0` |
| `agents.navigation.controller` 없음 | [A] | `export CARLA_ROOT=~/carla` |
| 서버 재시작 중 클라이언트 | [A] | 오류 출력 후 자동 재접속(로드맵 4). 궤적 나이 3 s 초과 시 정지(로드맵 6) |

---

## 9. 종료

| 어디 | 명령 |
|---|---|
| [A] | 클라이언트 `Esc` 또는 Ctrl+C → CARLA 터미널 Ctrl+C |
| [B] | 서버 Ctrl+C 또는 `sudo systemctl stop alpamayo-server` |
| 비용 | 실험 없을 때 두 인스턴스 모두 stop. open-loop만 할 때는 A를 stop |

---

## 10. 공식 Alpamayo 1.5 노트북  [B]

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
