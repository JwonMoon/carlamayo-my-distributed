# 설계 결정 기록 (ADR)

이 폴더는 "왜 이렇게 만들었는가"를 남긴다. 각 파일은 결정 하나를 다루며 다음 여섯 절로 짧게
쓴다: **상황 / 후보 / 결정 / 이유 / 탈락 이유 / 결과**. 결정이 뒤집히면 파일을 지우지 말고
상태를 `대체됨`으로 바꾸고 새 번호를 만든다.

| 번호 | 제목 | 상태 |
|---|---|---|
| [0001](0001-topology-client-on-sim-host.md) | 루프 클라이언트를 CARLA 인스턴스에 둔다 | 채택 |
| [0002](0002-rpc-transport-grpc.md) | 인스턴스 간 추론 RPC는 gRPC | 채택 |
| [0003](0003-image-encoding-jpeg-default.md) | 이미지는 기본 JPEG, 진단용 raw | 채택 |
| [0004](0004-upstream-import-preserve-history.md) | 업스트림은 git 히스토리를 보존해 가져온다 | 채택 |
| [0005](0005-open-loop-in-split-env.md) | open-loop는 B 로컬 재생과 A 원격 재생 둘 다 지원 | 채택 |
| [0006](0006-pygame-ui-on-sim-host.md) | pygame UI는 A에서 DCV로 표시, 기본 ON, VQA는 정지형 유지 | 채택 |
| [0007](0007-run-dir-and-run-id.md) | 실행마다 결과 폴더를 만들고 run_id를 RPC로 전달해 두 호스트 폴더명을 맞춘다 | 채택 |

## 템플릿

```markdown
# NNNN. 제목

상태: 채택 | 대체됨(→ NNNN) | 폐기      날짜: YYYY-MM-DD

## 상황
## 후보
## 결정
## 이유
## 탈락 이유
## 결과
```
