# 0001. 루프 클라이언트를 CARLA 인스턴스에 둔다

상태: 채택      날짜: 2026-09-30

## 상황
CARLA 서버와 Alpamayo 모델을 서로 다른 AWS 인스턴스(A: g5.2xlarge, B: g6e.xlarge)로 나눈다.
지금은 한 Python 프로세스(`carlamayo.py`)가 CARLA 접속, 카메라 수집, 모델 추론, PID 제어를
전부 한다. 이 프로세스를 **어느 쪽에 둘 것인가**를 정해야 한다.

## 후보
- (a) **클라이언트를 A(CARLA 옆)에 두고, 모델만 B의 서버로 뺀다.**
- (b) 클라이언트를 B(GPU 옆)에 두고, 기존 `--carla-host` 플래그로 A의 CARLA에 원격 접속한다. 코드 변경이 거의 없다.

## 결정
(a). 클라이언트는 A에 남고, B에는 추론 서버만 둔다.

## 이유
- CARLA→클라이언트 센서 트래픽이 크다. 카메라 한 장이 8.3 MB(BGRA 1080p)이고 tick당 4~7장,
  10 Hz면 **300~600 MB/s**다(`carla_interface.py:288-302`). 클라이언트→모델 트래픽은 1초에
  한 번 JPEG 5~8 MB다. 큰 쪽을 loopback에 남기는 것이 맞다.
- Traffic Manager가 클라이언트 프로세스 안에서 돈다(`carla_interface.py:72-108`). 동기 모드에서
  NPC 50대의 오토파일럿은 tick마다 서버와 여러 번 RPC를 주고받으므로 네트워크를 건너면
  tick이 느려지고 불안정해진다.
- PID 추종기가 CARLA 설치 트리(`PythonAPI/carla/agents`)와 `carla.Transform`, 차량 객체를
  쓴다(`pid_controller.py:15-43, 121-155`). pygame UI, 리스폰, 영상 기록도 CARLA 객체를 쓴다.
  전부 A에 있는 편이 자연스럽다.
- A에서 torch를 제거할 수 있다. 새는 지점 다섯 곳이 전부 사소하다
  ([architecture-analysis.md §3](../architecture-analysis.md)).
- 장애 격리: 비싼 쪽(모델 로드 수 분)이 서버로 상주하고, 자주 재시작하는 쪽(CARLA, 루프)이
  가벼워진다.

## 탈락 이유
(b)는 코드 변경이 가장 적지만, 300~600 MB/s 센서 스트림과 TM RPC를 VPC 네트워크에 태운다.
10 Gbps라도 tick당 26~46 ms가 전송에만 든다. 또한 B의 py3.12 torch 환경에 `carla` 휠과
CARLA PythonAPI 트리를 함께 두어야 해서 환경 분리 효과가 사라진다.

## 결과
- 신규: `module/remote/client.py`(`RemoteAlpamayoAdapter`), `module/remote/server.py`, `alpamayo_server.py`.
- A의 설치 프로파일 `requirements-sim.txt`에는 torch가 없다.
- `--carla-host`는 그대로 남지만 문서상 "같은 호스트의 다른 포트" 용도로만 안내한다.
