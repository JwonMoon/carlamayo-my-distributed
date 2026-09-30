# 업스트림 대비 변경 기록

- 업스트림: `https://github.com/aveeslab/Carlamayo`, 리모트 이름 `upstream`
- 기준 커밋: `e6372ea` (Support Alpamayo 1 / 1.5 / 2 via --version and add a unified live-open-loop launcher)
- 이 저장소의 목적: 위 코드를 **CARLA 인스턴스 / Alpamayo 인스턴스로 분리 실행**하도록 개조

## 기록 규칙

1. 업스트림 코드를 고치거나 파일을 추가하는 커밋마다 아래 표에 한 줄 이상 추가한다.
2. "이유" 열에는 어떤 기능을 위해서인지 적고, 설계 근거가 있으면 [ADR](adr/README.md) 번호를 단다.
3. 로드맵 단계 번호([distributed-roadmap.md](distributed-roadmap.md))를 함께 적어 진행 상황을 추적한다.
4. 업스트림을 merge한 경우도 한 줄로 남긴다(어느 커밋까지 따라갔는지).

## 검증 기록

| 날짜 | 조건 | 결과 |
|---|---|---|
| 2026-09-30 | 가져온 직후, CI와 같은 의존성(CPU torch, numpy, scipy, pillow, opencv-headless, pytest), `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q tests` | **55 passed** |

## 변경 표

| 날짜 | 기능 | 파일 | 변경 내용 | 이유 / 근거 | 로드맵 |
|---|---|---|---|---|---|
| 2026-09-30 | 저장소 시작 | (전체) | `upstream/main`(`e6372ea`) 히스토리를 그대로 가져와 브랜치 시작. 서브모듈 gitlink 4개 유지, 초기화하지 않음 | [ADR 0004](adr/0004-upstream-import-preserve-history.md) | 0 |
| 2026-09-30 | 문서 | `docs/architecture-analysis.md` | 현재(단일 호스트) 구조 분석: 배포·모듈 의존·시퀀스·데이터 크기·환경·타이밍·UI 현황 | 분리 설계의 근거 | 1 |
| 2026-09-30 | 문서 | `docs/distributed-architecture.md` | 분리 후 토폴로지, 인스턴스 간 데이터 교환 명세, 시퀀스, pygame UI 방안, 전/후 비교, proto 초안, 리스크 | [ADR 0001~0003, 0005, 0006](adr/README.md) | 1 |
| 2026-09-30 | 문서 | `docs/adr/*.md` | 설계 결정 6건과 색인·템플릿 | 결정 이유와 탈락 후보 기록 요청 | 1 |
| 2026-09-30 | 문서 | `docs/distributed-roadmap.md` | 분리 구현 10단계, 파일·함수 단위 변경 목록 | 후속 구현 지침 | 1 |
| 2026-09-30 | 문서 | `docs/cheatsheet.md` | 인스턴스별 명령어 표 (구현 전 항목은 로드맵 단계 표시) | 운영 편의 | 1 |
| 2026-09-30 | 문서 | `docs/alpamayo15-notebooks-guide.md` | 공식 노트북 4개의 내용·준비물·g6e.xlarge 실행 가능성·예상 결과 | 모델 기능 사전 확인 | 1 |
| 2026-09-30 | 문서 | `docs/diagrams/*.svg` | 위 문서의 Mermaid 다이어그램을 SVG로 렌더링(mermaid-cli) | Mermaid 미지원 뷰어 대비 | 1 |
| 2026-09-30 | 문서 | `README.md` | 저장소 목적, 문서 색인, 업스트림 동기화 절 추가 | | 1 |
| 2026-09-30 | 문서(2차) | `docs/diagrams/README.md` | 다이어그램 11개 각각의 출처·의미·읽는 법 | 다이어그램 설명 요청 | 1 |
| 2026-09-30 | 문서(2차) | `docs/cheatsheet.md`, `docs/distributed-architecture.md`, `docs/distributed-roadmap.md`, `docs/adr/0005`, `docs/architecture-analysis.md` | "무엇이 어디서 도는가" 표와 세 모드 용어표 추가, `carlamayo.py`가 A에서 도는 이유 명시, S3 명령을 `rsync`/`scp`로 교체, 배포·open-loop 다이어그램 갱신 | 치트시트 혼동 해소, SSH 기반 운영에 맞춤 | 1 |
| 2026-09-30 | 문서(3차) | `docs/distributed-roadmap.md`, `docs/distributed-architecture.md` §9, `docs/adr/0007`, `docs/cheatsheet.md` | 실행 결과 폴더(`runs/<run_id>/`) 규칙과 run_id RPC 전달, 프로파일링(A/B 기록 항목, `tools/analyze_run.py`) 설계를 로드맵 1b·6b로 추가. 치트시트에 systemd 설명과 "B는 서버만 켜 두면 됨" 설명 | 재실행 시 덮어쓰기 방지, 보고서용 성능 기록 요청 | 1 |

> 코드 파일(`*.py`, `requirements-*.txt`, `pyproject.toml`, `.github/`)은 아직 업스트림과 동일하다.
