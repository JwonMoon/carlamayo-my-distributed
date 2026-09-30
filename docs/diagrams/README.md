# 다이어그램 설명

이 폴더의 SVG는 문서 안의 Mermaid 블록을 렌더링한 것이다. **원본은 각 문서의 Mermaid 코드**이며,
GitHub에서 문서를 열면 같은 그림이 바로 보인다. SVG는 Mermaid를 지원하지 않는 뷰어용이다.

## 현재 구조 (`architecture-analysis.md`)

| 파일 | 출처 | 보여주는 것 | 읽는 법 |
|---|---|---|---|
| `current-deployment.svg` | §2 | 지금은 한 호스트 안에 CARLA 서버 프로세스와 Carlamayo 클라이언트 프로세스(모델 포함)가 함께 있다는 것. CARLA와 클라이언트 사이의 포트(2000/2001/8000)와 GPU 사용 관계 | 실선 화살표는 데이터 흐름, 점선은 GPU 할당. 클라이언트 상자 안에 모델이 들어 있는 것이 핵심 |
| `current-module-dependencies.svg` | §3 | 어떤 Python 모듈이 어떤 모듈을 import하는지와, 각 모듈이 `carla`에 의존하는지 `torch`에 의존하는지 | **파랑** = `carla` 패키지 import(CARLA 인스턴스로), **주황** = `torch` import(모델 인스턴스로), **보라** = 둘 다(분리 대상인 루프 모듈), **회색** = 순수 Python/numpy(어느 쪽이든 가능). 화살표 = import 방향 |
| `seq-open-loop.svg` | §4.1 | `--loop open`의 흐름. CARLA 없이 녹화 데이터를 프레임마다 모델에 넣고 영상을 만든다 | 위에서 아래로 시간 순. `loop` 상자는 프레임 반복 |
| `seq-closed-loop-sync.svg` | §4.2 | `--loop closed`(기본, 동기)의 매 tick 흐름. 추론이 끝날 때까지 `world.tick()`이 멈춘다는 점 | `alt` 상자는 조건 분기. 추론 화살표에 "tick이 여기서 정지"라고 적힌 곳이 핵심 |
| `seq-closed-loop-async.svg` | §4.3 | `--loop closed --async`에서 tick 스레드와 추론 워커 스레드가 1슬롯 큐 두 개로 주고받는 방식과 stale 결과 폐기 | 참가자 5명: tick 스레드, 요청 큐, 워커, 결과 큐, 어댑터. `alt`에서 revision 비교로 옛 결과를 버린다 |
| `seq-navigation-cfg-prompt.svg` | §4.5 | navigation 모드에서 키보드로 "텍스트 \| 가중치"를 넣었을 때 어댑터가 CFG 샘플러를 고르기까지의 경로 | 가중치가 1.0이 아니면 CFG 경로, 1.0이면 일반 조건부 경로 |
| `seq-vqa.svg` | §4.6 | VQA 모드에서 궤적 추론 없이 질문·답변만 오가고 차량은 정지하는 흐름 | `loop` 안에 `apply_control(0,0,1.0)`(정지)이 매 tick 있음 |

## 분리 후 구조 (`distributed-architecture.md`)

| 파일 | 출처 | 보여주는 것 | 읽는 법 |
|---|---|---|---|
| `split-deployment.svg` | §2 | 두 인스턴스 배치. A(g5.2xlarge, `172.31.38.219`)에 CARLA 서버 + `carlamayo.py` + DCV, B(g6e.xlarge, `172.31.20.213`)에 `alpamayo_server.py` + 모델. 사이를 잇는 gRPC 한 줄과 파일 복사(scp/rsync) 경로 | 굵은 실선 = gRPC(요청 5~8 MB, 응답 < 10 KB, 약 1 Hz). A 안의 양방향 화살표 = loopback 센서 트래픽(300~600 MB/s). 점선 = 운영자 접속·파일 복사 |
| `split-seq-closed-loop-async.svg` | §4.1 | 분리 후 closed-loop(async). 시작 시 `GetModelInfo` 핸드셰이크로 카메라 리그를 받고, 워커 스레드가 JPEG 인코딩 후 `Predict`를 보내는 흐름 | 참가자 앞의 "A:"/"B:"가 어느 인스턴스에서 도는지. 핸드셰이크가 `CARLAInterface` 생성보다 먼저인 이유는 리그를 서버에서 받기 때문 |
| `split-seq-navigation-vqa-rpc.svg` | §4.2 | navigation(CFG) 가중치와 VQA 질문이 RPC 필드로 B에 전달되고 결과가 UI로 돌아오는 경로 | 위 절반이 navigation(`Predict`의 `navigation_weight`), 아래 절반이 VQA(`AnswerQuestion`) |
| `split-open-loop-two-paths.svg` | §4.3 | open-loop를 돌리는 두 경로. 경로 1 = 데이터를 B로 복사해 기존 코드 그대로 실행(기본). 경로 2 = A에서 원격 서버로 프레임을 보내며 실행(RPC 검증용) | 두 서브그래프가 각각 한 경로. 경로 2의 결과를 경로 1과 비교하는 것이 parity 테스트 |

## 다시 만들기

```bash
npm install @mermaid-js/mermaid-cli
# 문서에서 ```mermaid 블록을 .mmd로 꺼낸 뒤
npx mmdc -i diagram.mmd -o diagram.svg -b white
```

`docs/diagrams/*.svg`는 문서의 Mermaid를 수정할 때 함께 갱신한다.
