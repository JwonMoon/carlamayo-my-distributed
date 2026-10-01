# 데모 실행 순서서 (runbook)

데모 당일 **위에서 아래로 그대로 따라 치는** 문서다. 모든 옵션과 배경은 [cheatsheet.md](cheatsheet.md),
단계별 검증 상태는 [validation-checklist.md](validation-checklist.md)에 있다.

- **[A]** = 시뮬레이터 호스트 `172.31.38.219` (g5.2xlarge). CARLA, `carlamayo.py`, pygame 창(DCV). 명령은 DCV 세션 안의 터미널에서.
- **[B]** = 추론 호스트 `172.31.20.213` (g6e.xlarge). `alpamayo_server.py` 하나만 띄워 둔다.
- 순서: 0 점검 → 1 B 서버 → 2 A CARLA → 3 open-loop → 4 closed-loop 동기 → 4b 비동기 → 5 navigation+CFG → 6 VQA → 7 (선택) 후보 궤적 → 8 측정 정리 → 9 종료.
- 원칙: **B는 데모 내내 손대지 않는다.** 모드 전환(open/closed, navigation, CFG, VQA)은 전부 A의 플래그와 창 입력으로 한다.
- 터미널 규칙: B는 `tmux` 세션 `server`, A는 `tmux` 세션 `carla`(CARLA 서버) + DCV 터미널(클라이언트).

기록 칸의 `[ ]`는 실행 후 채운다. 이미 나온 값은 적어 두었다.

---

## 0. 시작 전 점검 (5분)

| 어디 | 명령 | 기대 |
|---|---|---|
| [A], [B] | `cd ~/carlamayo && git pull && git log -1 --oneline` | 두 곳 커밋이 같다 |
| [A] | `source venv-sim/bin/activate && export CARLA_ROOT=~/carla` | 이후 모든 A 명령의 전제 |
| [B] | `source a_venv/bin/activate && hf auth whoami` | 계정 이름이 나온다 |
| [B] | `ss -ltnp \| grep 50051` | 아직 서버가 없으면 빈 출력(정상). 1단계에서 띄운다 |
| [A] | `nc -zv 172.31.20.213 22` | `succeeded!` (보안그룹·SSH) |
| 로컬 PC | DCV 클라이언트로 A 접속 | 바탕화면이 보인다 |

> 팁: `nc`와 왕복 스니펫은 **A에서** 친다. B에서 치면 자기 자신을 보는 것이라 의미가 없다.

---

## 1. [B] 추론 서버 기동 (1회)

```bash
# [B]
tmux new -s server
cd ~/carlamayo && source a_venv/bin/activate
python alpamayo_server.py --version 1.5 --host 172.31.20.213 --port 50051
```

기대 로그(순서대로):
```
Loading Alpamayo 1.5 (...)...
Model loaded in NNNs. ...
Warm-up inference done in N.Ns.
SERVING Alpamayo 1.5 version=1.5 warmed_up=True cameras=4 NUM_FRAMES=4 IMG=1920x1080 num_traj_samples=1
```
`Ctrl+B, D`로 빠져나온다. 다시 보려면 `tmux attach -t server`.

| 확인 | 명령 | 기대 |
|---|---|---|
| VRAM | [B] `nvidia-smi` | 약 21~24 GB 사용 |
| 포트 | [A] `nc -zv 172.31.20.213 50051` | `succeeded!` |

기록: 모델 로드 `[ ]` s, 워밍업 `[ ]` s, VRAM `[ ]` GB (첫 실행은 22 GB 다운로드 때문에 수십 분).

> 팁: 서버가 안 떠 있으면 A의 클라이언트는 30초 뒤 `no inference server at 172.31.20.213:50051 after 30s`로 끝난다.
> 이 메시지를 보면 B의 `ss -ltnp | grep 50051`부터 확인한다. (2026-10-01에 실제로 겪음)

---

## 2. [A] CARLA 서버 기동 (1회)

```bash
# [A]
tmux new -s carla
cd ~/carla && ./CarlaUE4.sh -RenderOffScreen -quality-level=Epic
# Ctrl+B, D
nvidia-smi          # CarlaUE4 약 6 GB
```

> 팁: CARLA는 open-loop에는 필요 없고 closed-loop부터 필요하다. 미리 띄워 두면 4단계에서 기다리지 않는다.

---

## 3. [A] open-loop: 원격 추론 경로 검증

녹화 데이터 `carla_data/`가 있어야 한다(없으면 `python data_collect.py`를 1~2분 돌린 뒤 Ctrl+C).

```bash
# [A]
python carlamayo.py --loop open --version 1.5 --data-root carla_data \
  --inference-server 172.31.20.213:50051 --run-tag remote-jpeg
```

기대 터미널:
```
Run folder: runs/20261001-HHMMSS_open_v1.5_remote-jpeg     ← run_id (첫 줄 근처)
Inference: remote server at 172.31.20.213:50051
Total recorded frames: N
[Frame k] Inference: 2.xx s   ... 프레임마다 반복
```

끝나면 바로 정리한다.
```bash
# [A]
RUN=$(ls -t runs | head -1); echo $RUN
tools/fetch_server_profile.sh $RUN            # B의 profile_server*.csv → runs/$RUN/
python tools/analyze_run.py runs/$RUN         # summary.md + plots/*.png
sed -n 1,30p runs/$RUN/summary.md
```

결과 폴더 `runs/<run_id>/`: `carla_alpamayo_open_loop_result.mp4`(영상 위 궤적), `predictions.npz`, `args.json`, `log.txt`,
`profile_client*.csv`, (회수 후) `profile_server*.csv`, `summary.md`, `plots/`.

기록(summary.md headline): rtt_mean `[ ]` s, inference_mean `[ ]` s, overhead_mean `[ ]` s, request `[ ]` MB, upload `[ ]` Mbps.
(가짜 서버 왕복 2026-10-01: `rtt=0.177s request=0.5MB`, 검은 이미지라 요청이 작음)

> 팁: `rtt − server_total`이 0.5 s 미만이면 네트워크·인코딩은 병목이 아니다. 이 숫자가 발표의 "분리 비용" 근거다.

---

## 4. [A] closed-loop (normal, 동기 모드) — 주행 시연

```bash
# [A]  (DCV 터미널. SSH 터미널이면 먼저 export DISPLAY=:0)
python carlamayo.py --loop closed --version 1.5 --inference-server 172.31.20.213:50051 --run-tag sync
```

창(960×675)에서 볼 것:
- 카메라 영상 위 **빨간 선** = 따라가는 궤적(64점, 6.4 s). `--num-traj-samples`를 올렸을 때만 흰 후보선이 추가된다.
- 아래 패널: `RUNNING | frame N | NN.N km/h | steer 0.xx | inference 2.xx s`.
- 터미널: `[Frame k] Inference: 2.xx s`가 약 1초마다, 충돌 시 리스폰 메시지.

조작: `Ctrl+P` 일시정지/재개(시뮬 세계 전체가 멈춤), **`Esc` 종료**.

> 팁 1: **영상은 Esc(또는 Ctrl+C)로 끝내야 저장된다.** 프레임을 모았다가 종료 때 쓰기 때문이다. 창을 강제로 닫거나 터미널을 죽이면 안 남는다.
> 2~3분 단위로 끊어 돌리면 메모리도 안전하다(1080p 10분 ≈ 6 GB).
>
> 팁 2: 동기 모드에서는 **추론하는 동안 화면이 멈추는 것이 정상**이다(세계를 멈추고 그 장면에 맞는 궤적을 받음). 주행 품질 시연은 동기 모드로 한다.
>
> 팁 3: `--async`(비동기)는 화면이 끊기지 않지만 궤적이 왕복 시간만큼 오래된 장면 기준이라 커브·교차로에서 늦게 반응해 주행이 나빠진다.
> 패널의 `traj age`가 그 지연이다. 비동기는 "실시간성 vs 주행 품질" 설명과 측정 장표용으로만 쓴다.
>
> 팁 4: 창이 크거나 작으면 `--pygame-size 1280x900`처럼 바꾼다.

끝나면 3단계와 같이 `fetch_server_profile.sh` → `analyze_run.py`.
기록: 주행 관찰(차선 유지 / 교차로 / 앞차 감속) `[ ]`, inference_mean `[ ]` s, 궤적 나이 p95 `[ ]` s.

---

## 4b. [A] closed-loop (normal, 비동기 모드) — 실시간성 시연

동기 모드 바로 뒤에 같은 구간에서 돌려 **대비**를 보여준다.

```bash
# [A]
python carlamayo.py --loop closed --version 1.5 --async --inference-server 172.31.20.213:50051 --run-tag async
```

볼 것:
- 화면이 멈추지 않고 10 Hz로 계속 진행한다. 추론은 뒤에서 돌고 약 1초마다(실제로는 왕복 시간마다) 빨간 궤적이 교체된다.
- 터미널에 `Trajectory age: N.NN s`가 찍힌다(비동기에서만 출력). 이 값이 "궤적을 계산한 장면과 지금 장면의 시간 차"다.
  왕복 3 s에 시속 27 km면 약 20 m 전 장면 기준으로 달리는 셈이다.
- 커브·교차로에서 반응이 늦고 흔들린다. 네트워크가 끊기면 궤적 나이가 6 s를 넘는 순간 정지한다(안전장치).
- 2~3분 뒤 `Esc`.

설명 멘트: "늦는 이유는 분리가 아니라 모델 추론 시간이다. 네트워크·인코딩 몫은 0.2~0.4 s." → `summary.md`의
`inference_mean_s`(모델)와 `overhead_mean_s`(분리 비용)를 나란히 보여준다.

> 팁 1: 동기(4단계)와 비동기(4b)를 같은 출발점·같은 구간에서 돌려야 비교가 된다. 리스폰 위치가 같으므로 시작 직후 구간을 쓰면 된다.
>
> 팁 2: 두 run을 한 표로: `python tools/analyze_run.py compare runs/<sync> runs/<async>` → `compare.md`의 `traj_age` 열.
>
> 팁 3: 데모에서 주행 품질을 보여줄 때는 동기, 실시간성과 지연 수치를 보여줄 때는 비동기. 둘 다 서버는 그대로다.

기록: traj age 평균 `[ ]` s / p95 `[ ]` s, inference_mean `[ ]` s, overhead_mean `[ ]` s, 주행 소감 `[ ]`.

---

## 5. [A] navigation + CFG — 자연어 지시 시연

```bash
# [A]
python carlamayo.py --loop closed --version 1.5 --inference-server 172.31.20.213:50051 \
  --mode navigation --navigation-text "Turn right in 30m" --navigation-weight 1.5 --run-tag nav-cfg15
```

시연 흐름:
1. 시작하면 패널에 `Active nav: Turn right in 30m | weight: 1.50`이 보이고 바로 주행한다.
2. 주행 중 입력창에 `Turn left in 20m | 1.5`를 치고 **Enter**.
3. **확인**: 패널 `Active nav:` 줄이 새 지시로 바뀌고, 터미널에 `Navigation updated: Turn left in 20m (weight=1.50)`가 찍힌다. 다음 추론부터 반영된다(즉시가 아니라 1~3초 뒤).
4. 지시를 **해제**하려면 입력창을 비우고 `| 1.0`만 치고 Enter(또는 빈 줄 Enter). `Active nav: (no navigation text)`가 되면 normal과 같은 주행이다.

> 팁 1: **지시는 지울 때까지 매 추론에 그대로 들어간다.** "Turn right in 30m"을 두고 계속 달리면 모델은 매초 다시 우회전을 찾는다.
> 교차로 하나를 돌고 나면 바로 해제하거나 `Keep lane and go straight`로 바꿔야 정상 주행이 된다. (업스트림과 같은 동작)
>
> 팁 2: CFG 가중치 비교는 같은 구간에서 `| 1.0`과 `| 1.5`를 번갈아 넣고 궤적이 얼마나 지시 쪽으로 쏠리는지 본다. 1.5가 추론 시간이 조금 더 길다.
>
> 팁 3: 초기 지시 없이 `--mode navigation`만 주면 정지 상태로 시작한다. 입력 후 `Ctrl+P`로 출발.

기록: 지시 변경 반영 확인 `[ ]`, 1.0 vs 1.5 차이 `[ ]`, inference_mean(CFG) `[ ]` s.

---

## 6. [A] VQA — 질문·답 시연

```bash
# [A]
python carlamayo.py --loop closed --version 1.5 --inference-server 172.31.20.213:50051 \
  --mode vqa --vqa-question "What is ahead?" --run-tag vqa
```

시연 흐름:
1. 차량은 **정지**한 채(브레이크) 질문이 B로 간다. 패널 `VQA question: What is ahead?`.
2. 몇 초 뒤 패널 `Answer:` 줄과 터미널(`Q:` / `A:`)에 답이 나온다.
3. 입력창에 다른 질문(예: `Is there a traffic light?`)을 치고 Enter → `VQA question updated:` 출력 후 다시 1회 요청.

> 팁: VQA는 궤적을 만들지 않으므로 빨간 선이 없고 차가 서 있는 것이 정상이다. 주행하면서 묻는 모드는 없다(업스트림과 같음).

기록: 질문 2개와 답 `[ ]`, 응답 시간 `[ ]` s.

---

## 7. (선택) 궤적 후보 여러 개 — B 재시작 필요

```bash
# [B]  tmux attach -t server → Ctrl+C
python alpamayo_server.py --version 1.5 --host 172.31.20.213 --port 50051 --num-traj-samples 4
# [A]
python carlamayo.py --loop closed --version 1.5 --inference-server 172.31.20.213:50051 --run-tag samples4
```
흰 선 4개(후보) + 빨간 선 1개(선택). A 쪽 옵션은 없다(핸드셰이크로 서버 값을 받음). VRAM 약 30 GB, 추론 시간 증가.
**끝나면 B를 `--num-traj-samples` 없이 다시 띄워 기본 상태로 돌린다.** 데모 순서상 맨 마지막에 한다.

기록: inference_mean(4샘플) `[ ]` s vs 1샘플 `[ ]` s.

---

## 8. 측정 정리

```bash
# [A]  각 run_id마다 (3~7단계에서 안 했으면)
tools/fetch_server_profile.sh <run_id> && python tools/analyze_run.py runs/<run_id>
# 한 표로
python tools/analyze_run.py compare runs/<open> runs/<sync> runs/<async> runs/<nav-cfg15> runs/<vqa>    # → compare.md
```
```bash
# 로컬 PC: 영상·요약 가져오기
scp -r ubuntu@172.31.38.219:~/carlamayo/runs/<run_id> ./results/
```

---

## 9. 종료

| 순서 | 어디 | 명령 |
|---|---|---|
| 1 | [A] | 클라이언트 창에서 `Esc` (영상 저장 확인: `ls runs/<run_id>/*.mp4`) |
| 2 | [A] | `tmux attach -t carla` → Ctrl+C |
| 3 | [B] | `tmux attach -t server` → Ctrl+C |
| 4 | AWS | 실험이 없으면 두 인스턴스 stop (open-loop만 할 때는 A만 stop) |

---

## 부록. 자주 겪은 오류

| 증상 | 원인 | 조치 |
|---|---|---|
| `no inference server at 172.31.20.213:50051 after 30s` (`grpc.FutureTimeoutError`) | B에서 서버가 안 떠 있음, 또는 보안그룹이 50051을 막음 | [B] `ss -ltnp \| grep 50051`로 서버 확인 → 없으면 1단계. 있으면 [A] `nc -zv 172.31.20.213 50051` |
| `nc`가 멈춤(timed out) | 보안그룹 | B 인바운드에 A의 보안그룹(또는 `172.31.0.0/16`) TCP 22·50051 허용 |
| `nc` 즉시 `refused` | 포트는 열렸는데 서버 없음 / `--host` IP 오타 | [B]에서 서버 기동, `--host 172.31.20.213` 확인 |
| `nc`는 되는데 gRPC만 실패 | A의 `https_proxy` 환경변수로 gRPC가 프록시로 나감 | `export no_grpc_proxy=172.31.20.213` 또는 `unset https_proxy http_proxy` |
| `server is not warmed up` | 서버가 아직 모델 로드·워밍업 중 | B 로그에 `SERVING`이 뜰 때까지 대기 |
| `serves Alpamayo '2' but --version '1.5'` | A와 B의 `--version` 불일치 | 둘을 맞춘다 |
| `NUM_FRAMES: client 4 != server …` | 두 호스트의 커밋이 다름 | 양쪽 `git pull` |
| `DEADLINE_EXCEEDED` | 추론이 120 s를 넘김(샘플 수·CFG 과다) 또는 서버 멈춤 | `--rpc-timeout-sec` 조정, B 로그 확인 |
| pygame 창이 안 뜸 | DCV 세션 밖(SSH)에서 실행 | DCV 터미널에서 실행하거나 `export DISPLAY=:0` |
| `agents.navigation.controller` 없음 | `CARLA_ROOT` 미설정 | `export CARLA_ROOT=~/carla` |
| 영상이 없음 | 종료를 강제로 함(창 닫기·kill·세션 끊김) | `Esc` 또는 Ctrl+C로 종료. 폴더는 `runs/<run_id>/` |
| 주행이 흔들리고 늦게 반응 | 비동기 모드의 궤적 나이, 또는 지워지지 않은 navigation 지시 | 동기 모드로 / 지시 해제(`| 1.0` Enter) |
| 차가 안 움직임 | navigation/vqa 모드에서 정지 시작, 또는 궤적 나이 6 s 초과 안전장치 | `Ctrl+P`로 출발 / B 서버·네트워크 확인 |
