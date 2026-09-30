# 인스턴스별 명령어 치트시트

| 기호 | 인스턴스 | 내부 IP | 역할 |
|---|---|---|---|
| **[A]** | g5.2xlarge | `172.31.38.219` | CARLA 서버 + Carlamayo 클라이언트 + pygame UI(DCV) |
| **[B]** | g6e.xlarge | `172.31.20.213` | Alpamayo 추론 서버, 공식 노트북 |

> "(로드맵 N)" 표시가 붙은 명령은 [distributed-roadmap.md](distributed-roadmap.md)의 해당 단계가
> 구현된 뒤에 동작한다. 표시가 없는 명령은 지금 업스트림 코드로도 동작한다.

---

## 0. 최초 세팅

### [A] sim host

```bash
# 저장소
git clone https://github.com/jwonmoon/carlamayo-my-distributed.git ~/carlamayo
cd ~/carlamayo

# CARLA 0.9.16
mkdir -p ~/carla && cd ~/carla
wget https://tiny.carla.org/carla-0-9-16-linux
tar -xvzf carla-0-9-16-linux
export CARLA_ROOT=~/carla          # ~/.bashrc에 추가

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

---

## 1. 서버·시뮬레이터 기동

| 순서 | 어디 | 명령 | 확인 |
|---|---|---|---|
| 1 | [B] | `cd ~/carlamayo && source a_venv/bin/activate && python alpamayo_server.py --version 1.5 --host 172.31.20.213 --port 50051` (로드맵 5) | 로그에 `warmed_up=True`, `SERVING` |
| 1' | [B] | `sudo systemctl start alpamayo-server && journalctl -u alpamayo-server -f` (로드맵 9) | 같음 |
| 2 | [A] | `cd ~/carla && ./CarlaUE4.sh -RenderOffScreen -quality-level=Epic` | 별도 터미널, 유지 |
| 3 | [A] | `nvidia-smi` | CARLA가 약 6 GB 사용 |

---

## 2. 데이터 수집 [A]

```bash
cd ~/carlamayo && source venv-sim/bin/activate
python data_collect.py                     # Ctrl+C로 종료 → carla_data/ 생성
aws s3 sync carla_data s3://<bucket>/carla_data/      # B에서 open-loop 하려면
```

---

## 3. open-loop

| 경로 | 어디 | 명령 |
|---|---|---|
| 경로 1: B 로컬(기본) | [B] | `aws s3 sync s3://<bucket>/carla_data/ carla_data/ && python carlamayo.py --loop open --version 1.5 --data-root carla_data` |
| 경로 2: A 원격(parity) | [A] | `python carlamayo.py --loop open --version 1.5 --data-root carla_data --inference-server 172.31.20.213:50051` (로드맵 4) |
| 경로 2, raw | [A] | 위 명령에 `--image-encoding raw` |

출력: `carla_alpamayo_open_loop_result.mp4`

---

## 4. closed-loop [A]  (DCV 세션의 터미널에서 실행. SSH라면 `export DISPLAY=:0`)

| 모드 | 명령 |
|---|---|
| normal | `python carlamayo.py --loop closed --version 1.5 --async --inference-server 172.31.20.213:50051` (로드맵 4) |
| normal, UI 끔 | 위 + `--no-pygame-ui` (로드맵 7) |
| navigation, 초기 지시 | 위 + `--mode navigation --navigation-text "Turn right in 30m" --navigation-weight 1.0` |
| navigation + CFG | 위 + `--mode navigation --navigation-weight 1.5` (UI 입력창에 `텍스트 \| 1.5`) |
| vqa | 위 + `--mode vqa --vqa-question "What is ahead?"` (차량은 정지, 답은 패널·터미널) |
| 첫 프롬프트를 UI에서 받고 시작 | 위 + `--start-paused` (로드맵 7) |

UI 조작: `Enter` 프롬프트 적용, `Ctrl+P` 일시정지/재개(시뮬 세계 전체 정지), `Esc` 종료.
출력: `carla_alpamayo_closed_loop_result.mp4`, `carla_alpamayo_closed_loop_result_pygame_ui.mp4`

업스트림 코드 그대로(단일 호스트, 원격 없음)로 A에서만 돌리려면 `--inference-server`를 빼고
A에 모델 환경을 갖추면 된다. 이 경우 A의 24 GB로는 1.5가 빠듯하다(`--quantization` 권장).

---

## 5. live-open-loop [A]

```bash
python carlamayo.py --loop live-open --version 1.5 --async --inference-server 172.31.20.213:50051   # (로드맵 4)
```
출력: `carla_alpamayo_live_open_loop_result.mp4`

---

## 6. 결과 회수

| 어디 | 명령 |
|---|---|
| [A]/[B] | `aws s3 cp carla_alpamayo_*_result*.mp4 s3://<bucket>/results/$(date +%F)/` |
| 로컬 PC | `aws s3 sync s3://<bucket>/results/ ./results/` 또는 `scp` |

---

## 7. 상태 확인·문제 해결

| 목적 | 어디 | 명령 |
|---|---|---|
| 서버 health | [A] | `grpc_health_probe -addr=172.31.20.213:50051` 또는 `python -c "import grpc; ..."` (로드맵 5) |
| 포트 열림 | [A] | `nc -zv 172.31.20.213 50051` |
| GPU | [A]/[B] | `nvidia-smi` |
| 서버 로그 | [B] | `journalctl -u alpamayo-server -f` |
| CARLA 응답 | [A] | `python -c "import carla; c=carla.Client('localhost',2000); c.set_timeout(5); print(c.get_server_version())"` |
| pygame 창이 안 뜸 | [A] | DCV 세션 터미널에서 실행하거나 `export DISPLAY=:0` |
| `agents.navigation.controller` 없음 | [A] | `export CARLA_ROOT=~/carla` |
| 서버 재시작 중 클라이언트 | [A] | 오류 출력 후 자동 재접속(로드맵 4). 궤적 나이 3 s 초과 시 정지(로드맵 6) |

---

## 8. 종료

| 어디 | 명령 |
|---|---|
| [A] | 클라이언트 `Esc` 또는 Ctrl+C → CARLA 터미널 Ctrl+C |
| [B] | 서버 Ctrl+C 또는 `sudo systemctl stop alpamayo-server` |
| 비용 | 실험 없을 때 두 인스턴스 모두 stop. open-loop만 할 때는 A를 stop |

---

## 9. 공식 Alpamayo 1.5 노트북 [B]

[alpamayo15-notebooks-guide.md](alpamayo15-notebooks-guide.md) 참조.

```bash
cd ~/carlamayo/third_party/alpamayo1.5
source ~/carlamayo/a_venv/bin/activate
uv pip install mediapy ipykernel ipywidgets jupyter
jupyter notebook --no-browser --port 8888 --notebook-dir notebooks
# 로컬 PC:  ssh -N -L 8888:localhost:8888 <B>   → 브라우저 http://localhost:8888
```
