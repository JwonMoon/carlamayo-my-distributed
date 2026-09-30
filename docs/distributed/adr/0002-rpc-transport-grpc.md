# 0002. 인스턴스 간 추론 RPC는 gRPC

상태: 채택      날짜: 2026-09-30

## 상황
A(CARLA)에서 B(모델)로 1초에 한 번 이미지 스택(JPEG 5~8 MB, raw 100~174 MB)과 작은 배열을
보내고, 궤적(1 KB 미만)과 텍스트를 받아야 한다. closed-loop에서는 응답이 늦거나 유실되면
차량을 세워야 하므로 타임아웃과 실패 처리가 중요하다. A는 Python 3.10 또는 3.12, B는 3.12다.

## 후보
| 후보 | 한 줄 요약 |
|---|---|
| **gRPC** (protobuf + HTTP/2) | 스키마 파일이 계약서, deadline/상태코드/헬스체크/재연결 내장 |
| ZeroMQ + msgpack | 가장 가볍고 빠름, 요청-응답 짝짓기·타임아웃·재연결을 직접 구현 |
| Cap'n Proto RPC | zero-copy 직렬화로 가장 빠름, Python 바인딩(pycapnp) 성숙도와 생태계가 작음 |
| HTTP REST (FastAPI) | curl로 디버깅 최고, 이미지 배열 전송은 JSON/multipart 오버헤드로 비효율 |
| raw TCP 소켓 | 메시지 경계·직렬화·오류 처리를 전부 손으로 |

모두 TCP 위에서 동작한다. 차이는 "TCP 위의 메시지 형식·짝짓기·실패 처리를 얼마나 직접 짜는가"다.

## 결정
gRPC. 단, 전송 계층은 `RemoteAlpamayoAdapter` 한 클래스 뒤에 숨겨 나중에 교체할 수 있게 한다.

## 이유
선택 기준을 중요도 순으로 적용했다.
1. **병목이 어디인가.** 추론 시간(수 초)이 지배적이고 전송은 1 Hz에 수 MB다. 직렬화 속도
   차이(밀리초)는 체감되지 않는다. 그래서 "가장 빠른 것"이 아니라 "운영이 편한 것"을 고른다.
2. **실패 처리가 내장되어 있는가.** deadline, `UNAVAILABLE`/`DEADLINE_EXCEEDED`/
   `RESOURCE_EXHAUSTED` 상태 코드, 자동 재연결, 표준 헬스 서비스가 있다. closed-loop의 기존
   "Inference error" 경로에 그대로 매핑된다.
3. **두 호스트 간 계약이 명확한가.** 카메라 리그·버전·프레임 수가 어긋나면 조용히 잘못된
   결과가 나온다. `.proto` 하나가 양쪽의 계약서가 된다.
4. **설치.** `grpcio`는 py3.10·3.12 모두 바이너리 휠이 있어 A에서 빌드가 없다.
5. **AWS 운영.** systemd 헬스체크, 로드밸런서, TLS 전환이 표준 경로다.

## 탈락 이유
- ZeroMQ: 성능 이점(20~30 %)이 이 워크로드에서 무의미하고, REQ/REP는 응답 유실 시 소켓을
  다시 만들어야 하며 deadline·헬스·버전 협상을 직접 짜야 한다.
- Cap'n Proto: 전송량의 99 %가 이미지 바이트 덩어리라 zero-copy 이점이 거의 없다. pycapnp는
  빌드가 까다로운 경우가 있고 문서·도구가 적다.
- HTTP REST: base64/multipart로 33 % 이상 부풀고 스트리밍·deadline 이야기가 약하다.
- raw TCP: 위 모든 것을 직접 구현해야 한다.

## 결과
- `proto/alpamayo_inference.proto`, 생성 스텁 `module/remote/*_pb2*.py`를 커밋한다.
- 양쪽 `max_*_message_length = 512 MB`, keepalive 설정. 서버는 모델 호출 lock.
- 전송이 병목이 되는 상황(예: raw 이미지를 매 tick 전송)이 오면 `RemoteAlpamayoAdapter`
  내부만 ZeroMQ로 바꾸는 것이 교체 경로다.
