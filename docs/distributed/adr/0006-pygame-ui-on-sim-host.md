# 0006. pygame UI는 A에서 DCV로 표시, 기본 ON, VQA는 정지형 유지

상태: 채택      날짜: 2026-09-30

## 상황
사용자는 normal / navigation(CFG) / vqa 모든 closed-loop 모드에서 차량 주행 화면을 보고 싶다.
현재 `--pygame-ui`는 기본 OFF이고, 켜면 모드와 무관하게 일시정지로 시작하며, 일시정지 중에는
`tick()`을 건너뛰어 시뮬 세계 전체가 멈춘다(`closed_loop.py:90, 405-413`). live-open에는 UI가
없다. AWS 인스턴스는 헤드리스이며 A에 NICE DCV가 설정되어 있다.

## 후보
- 표시 위치: A에서 실행 / B에서 실행 / 별도 뷰어 호스트
- 표시 방법: NICE DCV / SSH X11 forwarding / 브라우저 MJPEG 뷰어(신규 코드)
- 시작 정지: 유지 / 제거 / 옵션화
- VQA: 정지형 유지 / 주행 중 VQA 모드 신설

## 결정
- UI는 **A에서** 실행하고 **NICE DCV** 세션에 표시한다.
- closed-loop에서 UI **기본 ON**(`--no-pygame-ui`로 해제). live-open에도 같은 UI(입력창 없음)를 붙인다.
- 시작 정지는 `--start-paused`로 **옵션화**. 기본은 normal 모드이거나 초기 프롬프트가 CLI로
  주어지면 즉시 주행, 아니면 정지.
- VQA는 **정지형 유지**. 주행 중 VQA 모드는 만들지 않는다.

## 이유
- UI가 그리는 카메라 프레임, 조향값, 속도, 충돌·리스폰 상태, 입력창은 전부 A의 루프 안에
  있다. B에는 1초에 한 번 압축 이미지가 올 뿐이다.
- DCV는 이미 설정되어 있고 EC2에서 무료이며 GPU 가속 데스크톱을 준다. 추가 코드가 없다.
- navigation 모드는 Ctrl+P로 한 번 재개한 뒤 주행하면서 Enter로 지시를 바꾸는 동작이 이미
  구현되어 있다(`closed_loop.py:391-404`). 부족한 것은 시작 정지를 끄는 옵션뿐이다.
- VQA는 모델의 텍스트 API(`generate_text`)가 궤적을 주지 않는다. 공식 노트북도 같은 구조다.
  주행 중 질문에 답하는 모드는 궤적 요청과 VQA 요청을 번갈아 보내야 해서 궤적 갱신이 늦어지고
  복잡도가 늘어난다. 사용자가 "원래대로"를 선택했다.

## 탈락 이유
- X11 forwarding: 1280×900을 10 Hz로 넘기기엔 느리다.
- MJPEG 웹 뷰어: 새 코드와 별도 포트가 필요하다. DCV가 있으므로 불필요. 나중에 필요해지면 추가.
- 주행 중 VQA: 위 이유로 보류.

## 결과
- 로드맵 7단계: `--no-pygame-ui`, `--start-paused`, live-open UI. RPC 계약과 무관한 A 쪽 변경.
- cheat sheet에 DCV 세션 안에서 실행하는 방법과 SSH 실행 시 `DISPLAY` 지정을 적는다.
